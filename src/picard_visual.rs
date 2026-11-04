//! The original Picard YTMND portrait, decoded locally after an explicit request.
//! No source image is compiled into the binary or included in a release archive.
//! Uses ordinary Ratatui cells instead of Kitty/iTerm graphics escapes: those
//! protocols require terminal capability negotiation and different cleanup rules.
//! Half-blocks work with the existing alternate-screen renderer, including over
//! SSH; truecolor/256-color and monochrome are explicit rendering adaptations.

use image::{ImageFormat, ImageReader, RgbImage, imageops::FilterType};
use ratatui::{Frame, layout::Rect, style::Color};
use sha2::{Digest, Sha256};
use std::{
    cell::RefCell,
    fs::{self, OpenOptions},
    io::{Cursor, Read, Write},
    os::{
        fd::AsRawFd,
        unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    },
    path::{Path, PathBuf},
    process::{Child, Stdio},
    time::{Duration, Instant},
};

pub const IMAGE_URL: &str =
    "https://users.content.ytmnd.com/f/8/c/f8cd26d2ab99e2f44562fb050d74c9a2.jpg";
const IMAGE_SHA256: &str = "5f35ea6e9fb61e7091da79b8c6086fff53f5aefacf778ad076214fcf6b0455bf";
const IMAGE_BYTES: usize = 58_375;
const IMAGE_WIDTH: u32 = 436;
const IMAGE_HEIGHT: u32 = 574;
const MAX_DOWNLOAD: usize = 1_048_576;
const CACHE_NAME: &str = "picard-f8cd26d2.jpg";

pub struct Visual {
    image: RgbImage,
    raster: RefCell<Option<Raster>>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
struct RasterKey {
    columns: u16,
    rows: u16,
    monochrome: bool,
    truecolor: bool,
}

struct Raster {
    key: RasterKey,
    cells: Vec<RasterCell>,
}

struct RasterCell {
    symbol: &'static str,
    foreground: Color,
    background: Color,
}

impl Visual {
    pub fn load_cancellable(
        state_dir: &Path,
        mut cancel: impl FnMut() -> bool,
    ) -> Result<Self, String> {
        check_cancel(&mut cancel)?;
        // Separate from the audio controller lock, so the image can load while
        // its excerpt is playing. Neither path reads the credential directory.
        let root = crate::picard::media_dir(state_dir)?.join("image");
        crate::store::private_dir(&root)?;
        crate::picard::private_directory(&root)?;
        let _lock = crate::envfile::lock_directory(&root)
            .map_err(|_| "Picard image cache is busy; try again")?;
        let bytes = cached_image(&root, &mut cancel)?;
        check_cancel(&mut cancel)?;
        Self::decode(&bytes)
    }

    fn decode(bytes: &[u8]) -> Result<Self, String> {
        // Check the exact known asset before invoking a decoder. Limits also
        // bound the JPEG decoder's dimensions and allocation independently.
        if !valid_image(bytes) {
            return Err("Picard image did not match its source checksum".into());
        }
        let mut reader = ImageReader::with_format(Cursor::new(bytes), ImageFormat::Jpeg);
        let mut limits = image::Limits::default();
        limits.max_image_width = Some(IMAGE_WIDTH);
        limits.max_image_height = Some(IMAGE_HEIGHT);
        limits.max_alloc = Some(8 * 1024 * 1024);
        reader.limits(limits);
        let image = reader
            .decode()
            .map_err(|_| "Cannot decode the original Picard image")?
            .to_rgb8();
        if image.dimensions() != (IMAGE_WIDTH, IMAGE_HEIGHT) {
            return Err("Unexpected dimensions in the Picard image".into());
        }
        Ok(Self::from_image(image))
    }

    fn from_image(image: RgbImage) -> Self {
        Self {
            image,
            raster: RefCell::new(None),
        }
    }

    fn rasterize(&self, key: RasterKey) -> Raster {
        let pixels = image::imageops::resize(
            &self.image,
            u32::from(key.columns),
            u32::from(key.rows) * 2,
            FilterType::Triangle,
        );
        let mut cells = Vec::with_capacity(usize::from(key.columns) * usize::from(key.rows));
        for row in 0..key.rows {
            for column in 0..key.columns {
                let top = pixels.get_pixel(u32::from(column), u32::from(row) * 2).0;
                let bottom = pixels
                    .get_pixel(u32::from(column), u32::from(row) * 2 + 1)
                    .0;
                cells.push(if key.monochrome {
                    let shade =
                        ((u32::from(luminance(top)) + u32::from(luminance(bottom))) / 2) as u8;
                    RasterCell {
                        symbol: ascii_shade(shade),
                        foreground: Color::Reset,
                        background: Color::Reset,
                    }
                } else {
                    RasterCell {
                        symbol: "▀",
                        foreground: pixel_color(top, key.truecolor),
                        background: pixel_color(bottom, key.truecolor),
                    }
                });
            }
        }
        Raster { key, cells }
    }

    /// Fits one portrait, or repeats it horizontally/vertically like the site's
    /// tiled background. Assumes the common terminal cell ratio of about 1:2.
    /// Half-blocks provide two samples per cell; monochrome uses ASCII luminance.
    /// This is a terminal rasterization of the actual JPEG, not invented art.
    pub fn render(&self, frame: &mut Frame, area: Rect, monochrome: bool, tiled: bool) {
        if area.is_empty() {
            return;
        }
        let (columns, rows) = fit_cells(self.image.width(), self.image.height(), area);
        if columns == 0 || rows == 0 {
            return;
        }
        let key = RasterKey {
            columns,
            rows,
            monochrome,
            truecolor: supports_truecolor(),
        };
        let mut cached = self.raster.borrow_mut();
        if cached.as_ref().is_none_or(|raster| raster.key != key) {
            *cached = Some(self.rasterize(key));
        }
        let Some(raster) = cached.as_ref() else {
            return;
        };
        let (x0, y0, width, height) = if tiled {
            (area.x, area.y, area.width, area.height)
        } else {
            (
                area.x + (area.width - columns) / 2,
                area.y + (area.height - rows) / 2,
                columns,
                rows,
            )
        };
        let buffer = frame.buffer_mut();
        for row in 0..height {
            for column in 0..width {
                let index =
                    usize::from(row % rows) * usize::from(columns) + usize::from(column % columns);
                let pixel = &raster.cells[index];
                if let Some(cell) = buffer.cell_mut((x0 + column, y0 + row)) {
                    cell.set_symbol(pixel.symbol)
                        .set_fg(pixel.foreground)
                        .set_bg(pixel.background);
                }
            }
        }
    }
}

fn fit_cells(width: u32, height: u32, area: Rect) -> (u16, u16) {
    if width == 0 || height == 0 || area.is_empty() {
        return (0, 0);
    }
    // Each row holds two nearly square half-block pixels. Integer ratios avoid
    // losing a row to floating-point rounding at an exact height constraint.
    let w = u64::from(width);
    let h = u64::from(height);
    let columns = u64::from(area.width);
    let rows = u64::from(area.height);
    if columns * h <= rows * 2 * w {
        (area.width, ((columns * h / (w * 2)) as u16).max(1))
    } else {
        (((rows * 2 * w / h) as u16).max(1), area.height)
    }
}

fn supports_truecolor() -> bool {
    matches!(
        std::env::var("COLORTERM").as_deref(),
        Ok("truecolor" | "24bit")
    ) || std::env::var("TERM").is_ok_and(|term| term.ends_with("-direct"))
}

fn pixel_color(rgb: [u8; 3], truecolor: bool) -> Color {
    if truecolor {
        Color::Rgb(rgb[0], rgb[1], rgb[2])
    } else {
        Color::Indexed(xterm_index(rgb))
    }
}

fn xterm_index(rgb: [u8; 3]) -> u8 {
    // Search the fixed xterm cube and grayscale ramp, not the user's mutable
    // first 16 palette entries. Luma alone would discard the red uniform.
    let levels = [0u8, 95, 135, 175, 215, 255];
    let mut best = (u32::MAX, 16u8);
    for r in 0..6 {
        for g in 0..6 {
            for b in 0..6 {
                let color = [levels[r], levels[g], levels[b]];
                let distance = rgb
                    .iter()
                    .zip(color)
                    .map(|(a, b)| (i32::from(*a) - i32::from(b)).pow(2) as u32)
                    .sum();
                if distance < best.0 {
                    best = (distance, 16 + (36 * r + 6 * g + b) as u8);
                }
            }
        }
    }
    for i in 0..24 {
        let value = 8 + i * 10;
        let distance = rgb
            .iter()
            .map(|a| (i32::from(*a) - i32::from(value)).pow(2) as u32)
            .sum();
        if distance < best.0 {
            best = (distance, 232 + i);
        }
    }
    best.1
}

fn luminance([r, g, b]: [u8; 3]) -> u8 {
    ((u32::from(r) * 2126 + u32::from(g) * 7152 + u32::from(b) * 722) / 10000) as u8
}

fn ascii_shade(value: u8) -> &'static str {
    const SHADES: [&str; 10] = [" ", ".", ":", "-", "=", "+", "*", "#", "%", "@"];
    SHADES[usize::from(value) * 9 / 255]
}

fn valid_image(bytes: &[u8]) -> bool {
    bytes.len() == IMAGE_BYTES && format!("{:x}", Sha256::digest(bytes)) == IMAGE_SHA256
}

fn check_cancel(cancel: &mut dyn FnMut() -> bool) -> Result<(), String> {
    if cancel() {
        Err("Picard image loading canceled".into())
    } else {
        Ok(())
    }
}

fn cached_image(root: &Path, cancel: &mut dyn FnMut() -> bool) -> Result<Vec<u8>, String> {
    let path = root.join(CACHE_NAME);
    let facts =
        crate::envfile::inspect(&path, None).map_err(|_| "Cannot inspect Picard image cache")?;
    if facts.symlink_component.is_some() {
        return Err("Picard image cache contains a symlink; refusing".into());
    }
    if facts.exists {
        if !facts.strict_ok() {
            return Err(
                "Picard image cache must be an owned private regular file under 1 MiB".into(),
            );
        }
        let before =
            fs::symlink_metadata(&path).map_err(|_| "Cannot inspect Picard image cache")?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)
            .map_err(|_| "Cannot read Picard image cache")?;
        let after = file
            .metadata()
            .map_err(|_| "Cannot inspect open Picard image cache")?;
        if (before.dev(), before.ino()) != (after.dev(), after.ino()) {
            return Err("Picard image cache changed; retry".into());
        }
        let mut bytes = Vec::new();
        file.take((MAX_DOWNLOAD + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| "Cannot read Picard image cache")?;
        if !valid_image(&bytes) {
            return Err("Picard image cache failed its source checksum; remove the image cache to download it again".into());
        }
        return Ok(bytes);
    }
    check_cancel(cancel)?;
    let curl = crate::picard::executable("curl")
        .ok_or("Picard image needs curl for its first download; use picard open")?;
    let child = crate::picard::clean_command(&curl, false)
        .args([
            "-q",
            "--fail",
            "--silent",
            "--proto",
            "=https",
            "--connect-timeout",
            "5",
            "--max-time",
            "20",
            "--max-filesize",
            "1048576",
            "--",
            IMAGE_URL,
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "Cannot fetch the Picard image; use picard open")?;
    let bytes = download(child, cancel)?;
    if !valid_image(&bytes) {
        return Err(
            "Downloaded image did not match the original Picard image; nothing cached".into(),
        );
    }
    check_cancel(cancel)?;
    let partial = root.join("image.part");
    if let Ok(meta) = fs::symlink_metadata(&partial) {
        if !meta.is_file()
            || meta.uid() != unsafe { libc::geteuid() }
            || meta.mode() & 0o777 != 0o600
        {
            return Err("Unsafe partial Picard image download; refusing".into());
        }
        fs::remove_file(&partial).map_err(|_| "Cannot clear interrupted image download")?;
    }
    struct Partial(PathBuf);
    impl Drop for Partial {
        fn drop(&mut self) {
            let _ = fs::remove_file(&self.0);
        }
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&partial)
        .map_err(|_| "Cannot create Picard image cache")?;
    let _partial = Partial(partial.clone());
    file.set_permissions(fs::Permissions::from_mode(0o600))
        .map_err(|_| "Cannot make Picard image cache private")?;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| "Cannot save Picard image cache")?;
    fs::rename(partial, path).map_err(|_| "Cannot finish Picard image cache")?;
    Ok(bytes)
}

struct Download(Child);
impl Drop for Download {
    fn drop(&mut self) {
        if self.0.try_wait().ok().flatten().is_none() {
            let _ = self.0.kill();
        }
        let _ = self.0.wait();
    }
}

fn download(child: Child, cancel: &mut dyn FnMut() -> bool) -> Result<Vec<u8>, String> {
    let mut child = Download(child);
    let mut output = child
        .0
        .stdout
        .take()
        .ok_or("Cannot read Picard image download")?;
    let fd = output.as_raw_fd();
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err("Cannot configure cancellable image download".into());
    }
    let deadline = Instant::now() + Duration::from_secs(25);
    let mut bytes = Vec::new();
    let mut buffer = [0u8; 8192];
    let mut eof = false;
    loop {
        check_cancel(cancel)?;
        if Instant::now() >= deadline {
            return Err("Picard image download timed out".into());
        }
        if !eof {
            match output.read(&mut buffer) {
                Ok(0) => eof = true,
                Ok(count) => {
                    if bytes.len() + count > MAX_DOWNLOAD {
                        return Err("Picard image download exceeded 1 MiB".into());
                    }
                    bytes.extend_from_slice(&buffer[..count]);
                    continue;
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::WouldBlock | std::io::ErrorKind::Interrupted
                    ) => {}
                Err(_) => return Err("Cannot read Picard image download".into()),
            }
        }
        if eof
            && let Some(status) = child
                .0
                .try_wait()
                .map_err(|_| "Cannot finish Picard image download")?
        {
            if !status.success() {
                return Err(
                    "Could not fetch the original Picard image; use picard open or try again later"
                        .into(),
                );
            }
            return Ok(bytes);
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{Terminal, backend::TestBackend};

    #[test]
    fn cancellation_before_load_creates_no_state() {
        let temp = tempfile::tempdir().unwrap();
        let state = temp.path().join("absent");
        assert!(Visual::load_cancellable(&state, || true).is_err());
        assert!(!state.exists());
    }

    #[test]
    fn corrupt_and_symlinked_cache_are_refused() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap().join("image");
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let cache = root.join(CACHE_NAME);
        fs::write(&cache, b"not the source").unwrap();
        fs::set_permissions(&cache, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(
            cached_image(&root, &mut || false)
                .unwrap_err()
                .contains("checksum")
        );
        fs::remove_file(&cache).unwrap();
        std::os::unix::fs::symlink(root.join("absent"), &cache).unwrap();
        assert!(cached_image(&root, &mut || false).is_err());
    }

    #[test]
    fn stalled_download_cancellation_reaps_owned_child() {
        let child = std::process::Command::new("/bin/sleep")
            .arg("30")
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        let pid = child.id();
        let started = Instant::now();
        let result = download(child, &mut || started.elapsed() > Duration::from_millis(75));
        assert!(result.unwrap_err().contains("canceled"));
        assert!(started.elapsed() < Duration::from_secs(2));
        assert_eq!(unsafe { libc::kill(pid as i32, 0) }, -1);
    }

    #[test]
    fn raster_aspect_and_bounds_are_preserved() {
        assert_eq!(fit_cells(436, 574, Rect::new(0, 0, 80, 24)), (36, 24));
        assert_eq!(fit_cells(436, 574, Rect::new(0, 0, 10, 20)), (10, 6));
        let visual = Visual::from_image(RgbImage::from_pixel(4, 4, image::Rgb([255, 0, 0])));
        let mut terminal = Terminal::new(TestBackend::new(20, 12)).unwrap();
        terminal
            .draw(|frame| visual.render(frame, Rect::new(2, 2, 10, 6), false, false))
            .unwrap();
        let buffer = terminal.backend().buffer();
        assert_eq!(buffer[(0, 0)].symbol(), " ");
        assert_eq!(buffer[(2, 2)].symbol(), "▀");
        assert_eq!(buffer[(11, 6)].symbol(), "▀");
        assert_eq!(buffer[(12, 6)].symbol(), " ");
    }

    #[test]
    fn monochrome_uses_only_ascii_and_tiling_fills_area() {
        let visual = Visual::from_image(RgbImage::from_pixel(4, 4, image::Rgb([255, 255, 255])));
        let mut terminal = Terminal::new(TestBackend::new(16, 12)).unwrap();
        terminal
            .draw(|frame| visual.render(frame, Rect::new(1, 1, 14, 10), true, true))
            .unwrap();
        let buffer = terminal.backend().buffer();
        for row in 1..11 {
            for col in 1..15 {
                assert_eq!(buffer[(col, row)].symbol(), "@");
            }
        }
        assert_eq!(buffer[(0, 0)].symbol(), " ");
        assert_eq!(xterm_index([255, 0, 0]), 196);
        assert_eq!(xterm_index([128, 128, 128]), 244);
    }
}

// Package license verifies a local signed entitlement. Ordinary use is offline.
// Provider credentials are never opened or sent to the licensing service.
package license

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const maxFile = 32 * 1024
const filename = "license.json"

// Release builds pin these values. They are never loaded from environment variables.
var Origin = "https://godmode.build"
var PublicKey = "BEt9G1xxh1F0zCLjxcChb0fsjg3dhTxiTtnglqOqgO4"
var KeyID = "godmode-2026-01"

var ErrMissing = errors.New("A Godmode license is required. Run godmode license activate.")
var ErrPreview = errors.New("Godmode's private download password is required.")
var uuidPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type Envelope struct {
	Payload   string `json:"payload"`
	Signature string `json:"signature"`
	KeyID     string `json:"key_id"`
}

type Claims struct {
	Schema         int      `json:"schema"`
	Product        string   `json:"product"`
	LicenseID      string   `json:"license_id"`
	InstallationID string   `json:"installation_id"`
	IssuedAt       int64    `json:"issued_at"`
	Kind           string   `json:"kind"`
	MaxMajor       int      `json:"max_major"`
	Features       []string `json:"features"`
	TestMode       bool     `json:"test_mode"`
	ExpiresAt      *int64   `json:"expires_at,omitempty"`
}

type Receipt struct {
	InstallationID    string   `json:"installation_id"`
	License           Envelope `json:"license"`
	DeactivationToken string   `json:"deactivation_token,omitempty"`
}

type Config struct {
	Home      string
	Version   string
	Origin    string
	KeyID     string
	PublicKey ed25519.PublicKey
	Client    *http.Client
	Now       func() time.Time
}

func Default(home, version string) (Config, error) {
	if home == "" {
		home = os.Getenv("GODMODE_HOME")
	}
	if home == "" {
		home = os.Getenv("GODMODE_CONFIG_DIR")
	}
	if home == "" {
		base, err := os.UserHomeDir()
		if err != nil {
			return Config{}, errors.New("Godmode could not find your home directory.")
		}
		home = filepath.Join(base, ".godmode")
	}
	absolute, err := filepath.Abs(home)
	if err != nil {
		return Config{}, errors.New("Godmode could not resolve its home directory.")
	}
	key, err := base64.RawURLEncoding.DecodeString(PublicKey)
	if err != nil || len(key) != ed25519.PublicKeySize {
		return Config{}, errors.New("This build has no valid Godmode license verification key.")
	}
	return Config{Home: absolute, Version: version, Origin: Origin, KeyID: KeyID,
		PublicKey: ed25519.PublicKey(key), Now: time.Now}, nil
}

func (c Config) Path() string { return filepath.Join(c.Home, filename) }

func decode(data []byte, out any) error {
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(out); err != nil {
		return errors.New("The license file is unreadable.")
	}
	var extra any
	if err := d.Decode(&extra); err != io.EOF {
		return errors.New("The license file is unreadable.")
	}
	return nil
}

func (c Config) Verify(e Envelope, installation string) (Claims, error) {
	return c.verify(e, installation, false)
}

func (c Config) verify(e Envelope, installation string, allowExpired bool) (Claims, error) {
	invalid := errors.New("The Godmode license signature is invalid. Run godmode license activate.")
	if len(c.PublicKey) != ed25519.PublicKeySize || e.KeyID != c.KeyID || len(e.Payload) > maxFile {
		return Claims{}, invalid
	}
	payload, err := base64.RawURLEncoding.DecodeString(e.Payload)
	if err != nil {
		return Claims{}, invalid
	}
	signature, err := base64.RawURLEncoding.DecodeString(e.Signature)
	if err != nil || !ed25519.Verify(c.PublicKey, payload, signature) {
		return Claims{}, invalid
	}
	var claims Claims
	if err := decode(payload, &claims); err != nil {
		return Claims{}, err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(payload, &fields); err != nil {
		return Claims{}, invalid
	}
	for _, name := range []string{"schema", "product", "license_id", "installation_id", "issued_at", "kind", "max_major", "features", "test_mode"} {
		value, present := fields[name]
		if !present || bytes.Equal(value, []byte("null")) {
			return Claims{}, errors.New("The signed license is missing required terms.")
		}
	}
	if _, present := fields["expires_at"]; present && !claims.TestMode {
		return Claims{}, errors.New("The paid license must not contain an expiry.")
	}
	if claims.Schema != 1 || claims.Product != "godmode-cli" ||
		!uuidPattern.MatchString(claims.LicenseID) || !uuidPattern.MatchString(claims.InstallationID) ||
		claims.InstallationID != installation || claims.IssuedAt < 1 || claims.MaxMajor < 0 {
		return Claims{}, errors.New("This license does not match this Godmode installation.")
	}
	now := time.Now()
	if c.Now != nil {
		now = c.Now()
	}
	if claims.IssuedAt > now.Add(10*time.Minute).Unix() {
		return Claims{}, errors.New("This license was issued in the future. Check your system clock.")
	}
	if claims.TestMode {
		if claims.Kind != "evaluation" || claims.ExpiresAt == nil || *claims.ExpiresAt <= claims.IssuedAt || *claims.ExpiresAt > claims.IssuedAt+7*24*60*60 {
			return Claims{}, errors.New("The evaluation license has invalid dates.")
		}
		if !allowExpired && now.Unix() >= *claims.ExpiresAt {
			return Claims{}, errors.New("This evaluation license has expired. Activate a purchased Godmode license.")
		}
	} else if claims.Kind != "perpetual" || claims.ExpiresAt != nil {
		return Claims{}, errors.New("The paid license has invalid entitlement terms.")
	}
	major, err := strconv.Atoi(strings.Split(strings.TrimPrefix(c.Version, "v"), ".")[0])
	if err != nil || major > claims.MaxMajor {
		return Claims{}, errors.New("This Godmode version is outside your license. Your earlier version remains licensed.")
	}
	for _, feature := range claims.Features {
		if feature == "cli" {
			return claims, nil
		}
	}
	return Claims{}, errors.New("This license does not include the Godmode CLI.")
}

func secureInfo(path string, directory bool) error {
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || (directory && !info.IsDir()) || (!directory && !info.Mode().IsRegular()) {
		return errors.New("The license path must be a regular file in a real directory.")
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || int(stat.Uid) != os.Geteuid() || info.Mode().Perm()&0022 != 0 || (!directory && info.Mode().Perm()&0077 != 0) {
		return errors.New("The license path must be owned by you and private. Use mode 600 for license.json.")
	}
	return nil
}

func (c Config) Read() (Receipt, Claims, error) {
	return c.read(false)
}

func (c Config) read(allowExpired bool) (Receipt, Claims, error) {
	var receipt Receipt
	if err := secureInfo(c.Home, true); err != nil {
		if os.IsNotExist(err) {
			return receipt, Claims{}, ErrMissing
		}
		return receipt, Claims{}, err
	}
	if err := secureInfo(c.Path(), false); err != nil {
		if os.IsNotExist(err) {
			return receipt, Claims{}, ErrMissing
		}
		return receipt, Claims{}, err
	}
	f, err := os.OpenFile(c.Path(), os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return receipt, Claims{}, errors.New("Godmode could not read its license file.")
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, maxFile+1))
	if err != nil || len(data) > maxFile {
		return receipt, Claims{}, errors.New("The license file is unreadable.")
	}
	if err := decode(data, &receipt); err != nil {
		return receipt, Claims{}, err
	}
	claims, err := c.verify(receipt.License, receipt.InstallationID, allowExpired)
	if err != nil {
		return receipt, Claims{}, err
	}
	id, err := c.readInstallationID()
	if err != nil {
		return receipt, Claims{}, errors.New("The installation ID is missing or unreadable. Restore installation.json or import your saved license.")
	}
	if id != receipt.InstallationID {
		return receipt, Claims{}, errors.New("This license belongs to a different installation.")
	}
	return receipt, claims, nil
}

func (c Config) save(receipt Receipt) error {
	if _, err := c.Verify(receipt.License, receipt.InstallationID); err != nil {
		return err
	}
	if err := os.MkdirAll(c.Home, 0700); err != nil {
		return errors.New("Godmode could not create its license directory.")
	}
	if err := secureInfo(c.Home, true); err != nil {
		return err
	}
	unlock, err := c.lock()
	if err != nil {
		return err
	}
	defer unlock()
	id, err := c.readInstallationID()
	if os.IsNotExist(err) {
		err = c.writeInstallationID(receipt.InstallationID)
		id = receipt.InstallationID
	}
	if err != nil {
		return err
	}
	if id != receipt.InstallationID {
		return errors.New("This license belongs to a different installation. Use a fresh Godmode home to restore a backup.")
	}
	if err := secureInfo(c.Path(), false); err != nil && !os.IsNotExist(err) {
		return err
	}
	data, err := json.MarshalIndent(receipt, "", "  ")
	if err != nil || len(data) > maxFile {
		return errors.New("The license response is unreadable.")
	}
	f, err := os.CreateTemp(c.Home, ".license-*")
	if err != nil {
		return errors.New("Godmode could not save the license file.")
	}
	name := f.Name()
	defer os.Remove(name)
	if _, err = f.Write(append(data, '\n')); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil || closeErr != nil {
		return errors.New("Godmode could not save the license file.")
	}
	if err := os.Rename(name, c.Path()); err != nil {
		return errors.New("Godmode could not save the license file.")
	}
	return nil
}

func newID() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", errors.New("Godmode could not create an installation ID.")
	}
	b[6], b[8] = (b[6]&0x0f)|0x40, (b[8]&0x3f)|0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:]), nil
}

// Kernel-held locks release automatically on normal exit, signals, and crashes.
// The private lock file stays in place so concurrent processes share one inode.
func (c Config) lock() (func(), error) {
	if err := os.MkdirAll(c.Home, 0700); err != nil {
		return nil, errors.New("Godmode could not create its license directory.")
	}
	if err := secureInfo(c.Home, true); err != nil {
		return nil, err
	}
	path := filepath.Join(c.Home, ".license-lock")
	if err := secureInfo(path, false); err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	file, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return nil, errors.New("Godmode could not open its private license lock.")
	}
	if err := secureInfo(path, false); err != nil {
		file.Close()
		return nil, err
	}
	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		file.Close()
		return nil, errors.New("Another license change is in progress. Retry after it finishes.")
	}
	return func() { syscall.Flock(int(file.Fd()), syscall.LOCK_UN); file.Close() }, nil
}

func (c Config) readInstallationID() (string, error) {
	path := filepath.Join(c.Home, "installation.json")
	if err := secureInfo(path, false); err != nil {
		return "", err
	}
	f, err := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return "", err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, 1025))
	var saved struct {
		ID string `json:"installation_id"`
	}
	if err != nil || len(data) > 1024 || decode(data, &saved) != nil || !uuidPattern.MatchString(saved.ID) {
		return "", errors.New("Godmode's installation ID is unreadable.")
	}
	return saved.ID, nil
}

func (c Config) writeInstallationID(id string) error {
	path := filepath.Join(c.Home, "installation.json")
	data, _ := json.Marshal(map[string]string{"installation_id": id})
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return errors.New("Godmode could not save its installation ID.")
	}
	_, err = f.Write(append(data, '\n'))
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil || closeErr != nil {
		return errors.New("Godmode could not save its installation ID.")
	}
	return nil
}

// Random identity persists before activation so network retries reuse one slot.
func (c Config) installationID() (string, error) {
	unlock, err := c.lock()
	if err != nil {
		return "", err
	}
	defer unlock()
	id, err := c.readInstallationID()
	if err == nil {
		return id, nil
	}
	if !os.IsNotExist(err) {
		return "", err
	}
	if _, err := os.Lstat(c.Path()); err == nil {
		return "", errors.New("Restore installation.json or import your saved license before reactivating.")
	}
	id, err = newID()
	if err != nil {
		return "", err
	}
	return id, c.writeInstallationID(id)
}

func (c Config) request(path string, body any, password string, reply any) error {
	origin, err := url.Parse(c.Origin)
	if err != nil || origin.Scheme != "https" || origin.Host == "" || origin.User != nil || origin.Path != "" || origin.RawQuery != "" || origin.Fragment != "" {
		return errors.New("This build has an invalid licensing origin.")
	}
	data, err := json.Marshal(body)
	if err != nil {
		return errors.New("Godmode could not create the license request.")
	}
	req, err := http.NewRequest(http.MethodPost, c.Origin+path, bytes.NewReader(data))
	if err != nil {
		return errors.New("Godmode could not create the license request.")
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	if password != "" {
		req.SetBasicAuth("godmode", password)
	}
	client := &http.Client{Timeout: 20 * time.Second}
	if c.Client != nil {
		*client = *c.Client
	}
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	res, err := client.Do(req)
	if err != nil {
		return errors.New("Godmode could not reach the license service. Your saved license is unchanged.")
	}
	defer res.Body.Close()
	if res.StatusCode == http.StatusUnauthorized && strings.HasPrefix(strings.ToLower(res.Header.Get("WWW-Authenticate")), "basic") {
		return ErrPreview
	}
	if res.StatusCode != http.StatusOK {
		switch res.StatusCode {
		case http.StatusUnauthorized, http.StatusForbidden:
			return errors.New("The license service refused this license or installation.")
		case http.StatusConflict:
			return errors.New("This license has reached its activation limit. Deactivate another installation or contact support.")
		case http.StatusTooManyRequests:
			return errors.New("Too many license requests. Try again later.")
		default:
			return errors.New("The license service could not complete this request. Your saved license is unchanged.")
		}
	}
	data, err = io.ReadAll(io.LimitReader(res.Body, maxFile+1))
	if err != nil || len(data) > maxFile {
		return errors.New("The license service returned an unreadable response.")
	}
	return decode(data, reply)
}

func (c Config) Activate(key, password string) (Claims, error) {
	key = strings.TrimSpace(key)
	if len(key) < 16 || len(key) > 512 || strings.ContainsAny(key, "\r\n\x00\t ") {
		return Claims{}, errors.New("Enter the license key from your purchase.")
	}
	if err := secureInfo(c.Path(), false); err != nil && !os.IsNotExist(err) {
		return Claims{}, err
	}
	id, err := c.installationID()
	if err != nil {
		return Claims{}, err
	}
	var response struct {
		License           Envelope `json:"license"`
		DeactivationToken string   `json:"deactivation_token"`
	}
	body := map[string]string{"license_key": key, "installation_id": id, "platform": runtime.GOOS + "-" + runtime.GOARCH, "version": c.Version}
	if err := c.request("/api/licenses/activate", body, password, &response); err != nil {
		return Claims{}, err
	}
	claims, err := c.Verify(response.License, id)
	if err != nil {
		return Claims{}, err
	}
	if len(response.DeactivationToken) < 16 || len(response.DeactivationToken) > 1024 {
		return Claims{}, errors.New("The license service returned an unreadable response.")
	}
	receipt := Receipt{InstallationID: id, License: response.License, DeactivationToken: response.DeactivationToken}
	if err := c.save(receipt); err != nil {
		return Claims{}, err
	}
	return claims, nil
}

func (c Config) Import(data []byte) (Claims, error) {
	if len(data) > maxFile {
		return Claims{}, errors.New("The license file is too large.")
	}
	var receipt Receipt
	if err := decode(data, &receipt); err != nil {
		return Claims{}, err
	}
	claims, err := c.Verify(receipt.License, receipt.InstallationID)
	if err != nil {
		return Claims{}, err
	}
	return claims, c.save(receipt)
}

func (c Config) Deactivate(password string) error {
	receipt, claims, err := c.read(true)
	if err != nil {
		return err
	}
	if receipt.DeactivationToken == "" {
		return errors.New("This imported license has no deactivation token. Contact support to release its activation.")
	}
	var response struct {
		Deactivated bool `json:"deactivated"`
	}
	body := map[string]string{"license_id": claims.LicenseID, "installation_id": receipt.InstallationID, "deactivation_token": receipt.DeactivationToken}
	if err := c.request("/api/licenses/deactivate", body, password, &response); err != nil {
		return err
	}
	if !response.Deactivated {
		return errors.New("The license service did not confirm deactivation.")
	}
	unlock, err := c.lock()
	if err != nil {
		return err
	}
	defer unlock()
	current, _, err := c.read(true)
	if err != nil || current != receipt {
		return errors.New("Activation released. The local license changed during the request and was retained.")
	}
	if err := os.Remove(c.Path()); err != nil {
		return errors.New("Activation released. Godmode could not remove the local license file.")
	}
	return nil
}

//go:build !nomusic

package core

// NewMusicPack reads only installation state through the lightweight manager.
// The separately installed pack owns the audio interface and engine.
func NewMusicPack(home string) (*Client, error) {
	args := []string{"music", "__manager"}
	if home != "" {
		args = append([]string{"--home", home}, args...)
	}
	return newClient(args)
}

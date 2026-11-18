//go:build !nomusic

package main

import (
	"fmt"
	"os"

	"github.com/lofimichael/godmode-cli/internal/core"
	"github.com/lofimichael/godmode-cli/internal/musicpackui"
)

// The core delegates to the separately installed pack. It never links its
// player UI, synth, instruments, or jingle implementation.
func runMusic(r route) int {
	client, err := core.NewMusicPack(r.home)
	if err != nil {
		fmt.Fprintln(os.Stderr, "godmode:", err)
		return 1
	}
	state, err := client.Call("state", nil)
	client.Abort()
	client.Close()
	if err != nil {
		fmt.Fprintln(os.Stderr, "godmode:", err)
		return 1
	}
	if state["installed"] != true {
		install, err := musicpackui.Run()
		if err != nil {
			fmt.Fprintln(os.Stderr, "godmode:", err)
			return 1
		}
		if !install {
			return 0
		}
		if code := core.Run(append(selectedArgs(r, "music"), "install")); code != 0 {
			return code
		}
	}
	args := selectedArgs(r, "music")
	if r.noMotion {
		args = append(args, "--no-motion")
	}
	return core.Run(args)
}

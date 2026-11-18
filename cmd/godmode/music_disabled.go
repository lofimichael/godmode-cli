//go:build nomusic

package main

import "github.com/lofimichael/godmode-cli/internal/core"

func runMusic(r route) int { return core.Run(selectedArgs(r, "music")) }

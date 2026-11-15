// This test-only key is never trusted by a production build.
package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

func main() {
	seed := sha256.Sum256([]byte("Godmode synthetic test signing key. Not valid for production."))
	private := ed25519.NewKeyFromSeed(seed[:])
	if len(os.Args) == 2 && os.Args[1] == "--public-key" {
		fmt.Println(base64.RawURLEncoding.EncodeToString(private.Public().(ed25519.PublicKey)))
		return
	}
	if len(os.Args) != 3 || os.Args[1] != "--home" {
		os.Exit(2)
	}
	home := os.Args[2]
	now := time.Now().Unix()
	claims := map[string]any{"schema": 1, "product": "godmode-cli", "license_id": "87654321-1234-4123-8123-123456789abc", "installation_id": "12345678-1234-4123-8123-123456789abc", "issued_at": now, "kind": "evaluation", "expires_at": now + 604800, "max_major": 1, "features": []string{"cli"}, "test_mode": true}
	payload, _ := json.Marshal(claims)
	receipt := map[string]any{"installation_id": claims["installation_id"], "license": map[string]string{"payload": base64.RawURLEncoding.EncodeToString(payload), "signature": base64.RawURLEncoding.EncodeToString(ed25519.Sign(private, payload)), "key_id": "godmode-2026-01"}}
	data, _ := json.MarshalIndent(receipt, "", "  ")
	if err := os.MkdirAll(home, 0700); err != nil {
		panic(err)
	}
	if err := os.WriteFile(filepath.Join(home, "license.json"), append(data, '\n'), 0600); err != nil {
		panic(err)
	}
	identity, _ := json.Marshal(map[string]any{"installation_id": claims["installation_id"]})
	if err := os.WriteFile(filepath.Join(home, "installation.json"), append(identity, '\n'), 0600); err != nil {
		panic(err)
	}
}

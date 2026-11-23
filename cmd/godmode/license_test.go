package main

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"io"
	"os"
	"strings"
	"testing"
	"time"

	"godmode.build/cli/internal/license"
)

func TestLicenseKeyArgumentsAreNotAccepted(t *testing.T) {
	if code := licenseCommand([]string{"license", "activate", "synthetic-secret-value"}, t.TempDir()); code != 2 {
		t.Fatal("command line key accepted")
	}
}

func TestLicenseStatusExplainsLifetimeAndLegacyCoverage(t *testing.T) {
	public, private, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	originalKey, originalID := license.PublicKey, license.KeyID
	originalVersion := version
	version = "0.16.0"
	license.PublicKey = base64.RawURLEncoding.EncodeToString(public)
	license.KeyID = "synthetic-status"
	t.Cleanup(func() {
		license.PublicKey, license.KeyID = originalKey, originalID
		version = originalVersion
	})
	for _, maxMajor := range []int{0, 1} {
		home := t.TempDir()
		config, err := license.Default(home, version)
		if err != nil {
			t.Fatal(err)
		}
		claims := license.Claims{Schema: 1, Product: "godmode-cli", LicenseID: "87654321-1234-4123-8123-123456789abc",
			InstallationID: "12345678-1234-4123-8123-123456789abc", IssuedAt: time.Now().Unix(), Kind: "perpetual",
			MaxMajor: maxMajor, Features: []string{"cli"}}
		payload, _ := json.Marshal(claims)
		envelope := license.Envelope{Payload: base64.RawURLEncoding.EncodeToString(payload), KeyID: license.KeyID,
			Signature: base64.RawURLEncoding.EncodeToString(ed25519.Sign(private, payload))}
		receipt, _ := json.Marshal(license.Receipt{InstallationID: claims.InstallationID, License: envelope})
		if _, err := config.Import(receipt); err != nil {
			t.Fatal(err)
		}
		reader, writer, err := os.Pipe()
		if err != nil {
			t.Fatal(err)
		}
		stdout := os.Stdout
		os.Stdout = writer
		code := licenseCommand([]string{"license", "status"}, home)
		os.Stdout = stdout
		writer.Close()
		output, err := io.ReadAll(reader)
		reader.Close()
		if err != nil || code != 0 {
			t.Fatal("license status failed", code, err)
		}
		expected := "All local CLI versions, including future updates; offline verification"
		if maxMajor != 0 {
			expected = "Versions through 1.x; offline verification"
		}
		if !strings.Contains(string(output), expected) {
			t.Fatalf("coverage missing from status: %s", output)
		}
	}
}

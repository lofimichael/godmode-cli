package main

import "testing"

func TestInspectionNeverUsesAChildHelpFlagToBypassLicense(t *testing.T) {
	for _, args := range [][]string{{"__ui", "--help"}, {"__ui", "--version"}, {"run", "TOKEN", "--", "tool", "--help"}, {"--home", "/tmp/example", "set", "TOKEN"}, {"profile", "get", "business_name"}, nil} {
		if inspection(args) {
			t.Fatalf("licensed operation exempt: %q", args)
		}
	}
	for _, args := range [][]string{{"run", "--help"}, {"help"}, {"license", "status"}, {"--home", "/tmp/example", "list"}, {"--version"}, {"source"}, {"build-info"}} {
		if !inspection(args) {
			t.Fatalf("inspection blocked: %q", args)
		}
	}
}

func TestLicenseKeyArgumentsAreNotAccepted(t *testing.T) {
	if code := licenseCommand([]string{"license", "activate", "synthetic-secret-value"}, t.TempDir()); code != 2 {
		t.Fatal("command line key accepted")
	}
}

package license

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const testID = "12345678-1234-4123-8123-123456789abc"
const testLicense = "87654321-1234-4123-8123-123456789abc"

func fixture(t *testing.T) (Config, ed25519.PrivateKey, Claims) {
	t.Helper()
	public, private, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	c := Config{Home: filepath.Join(t.TempDir(), ".godmode"), Version: "0.16.0", KeyID: "synthetic", PublicKey: public, Now: func() time.Time { return time.Unix(1800000000, 0) }}
	claims := Claims{Schema: 1, Product: "godmode-cli", LicenseID: testLicense, InstallationID: testID, IssuedAt: 1700000000, Kind: "perpetual", MaxMajor: 1, Features: []string{"cli"}, TestMode: false}
	return c, private, claims
}

func sign(t *testing.T, c Config, private ed25519.PrivateKey, claims Claims) Envelope {
	t.Helper()
	payload, err := json.Marshal(claims)
	if err != nil {
		t.Fatal(err)
	}
	return Envelope{Payload: base64.RawURLEncoding.EncodeToString(payload), Signature: base64.RawURLEncoding.EncodeToString(ed25519.Sign(private, payload)), KeyID: c.KeyID}
}

func TestOfflineSignatureAndEntitlementBoundaries(t *testing.T) {
	c, private, claims := fixture(t)
	envelope := sign(t, c, private, claims)
	if _, err := c.Verify(envelope, testID); err != nil {
		t.Fatal(err)
	}
	changes := map[string]func(*Claims){
		"wrong product":      func(v *Claims) { v.Product = "another-product" },
		"wrong installation": func(v *Claims) { v.InstallationID = testLicense },
		"wrong kind":         func(v *Claims) { v.Kind = "subscription" },
		"no feature":         func(v *Claims) { v.Features = nil },
		"future issue":       func(v *Claims) { v.IssuedAt = 1900000000 },
		"unknown schema":     func(v *Claims) { v.Schema = 2 },
		"invalid id":         func(v *Claims) { v.LicenseID = "not-a-uuid" },
	}
	for name, change := range changes {
		t.Run(name, func(t *testing.T) {
			modified := claims
			change(&modified)
			if _, err := c.Verify(sign(t, c, private, modified), testID); err == nil {
				t.Fatal("invalid claims accepted")
			}
		})
	}
	tampered := envelope
	tampered.Payload = base64.RawURLEncoding.EncodeToString([]byte(`{"schema":1}`))
	if _, err := c.Verify(tampered, testID); err == nil {
		t.Fatal("tampered payload accepted")
	}
	tampered = envelope
	tampered.KeyID = "other"
	if _, err := c.Verify(tampered, testID); err == nil {
		t.Fatal("unknown signing key accepted")
	}
	c.Version = "2.0.0"
	if _, err := c.Verify(envelope, testID); err == nil {
		t.Fatal("future major version accepted")
	}
	c.Version = "1.999.0"
	c.Now = func() time.Time { return time.Unix(2200000000, 0) }
	if _, err := c.Verify(envelope, testID); err != nil {
		t.Fatal("perpetual license expired", err)
	}
}

func TestEvaluationExpiryAndPaidTermsCannotBeConfused(t *testing.T) {
	c, private, claims := fixture(t)
	now := c.Now().Unix()
	expiry := now + 3600
	claims.Kind = "evaluation"
	claims.TestMode = true
	claims.IssuedAt = now
	claims.ExpiresAt = &expiry
	if _, err := c.Verify(sign(t, c, private, claims), testID); err != nil {
		t.Fatal(err)
	}
	c.Now = func() time.Time { return time.Unix(expiry, 0) }
	if _, err := c.Verify(sign(t, c, private, claims), testID); err == nil {
		t.Fatal("expired evaluation accepted")
	}
	c.Now = func() time.Time { return time.Unix(now, 0) }
	claims.ExpiresAt = nil
	if _, err := c.Verify(sign(t, c, private, claims), testID); err == nil {
		t.Fatal("unlimited evaluation accepted")
	}
	claims.Kind = "perpetual"
	if _, err := c.Verify(sign(t, c, private, claims), testID); err == nil {
		t.Fatal("test perpetual accepted")
	}
	claims.TestMode = false
	claims.ExpiresAt = &expiry
	if _, err := c.Verify(sign(t, c, private, claims), testID); err == nil {
		t.Fatal("expiring paid license accepted")
	}
	claims.Kind = "evaluation"
	if _, err := c.Verify(sign(t, c, private, claims), testID); err == nil {
		t.Fatal("evaluation without test flag accepted")
	}
	claims.TestMode = true
	expiry = now + 604801
	if _, err := c.Verify(sign(t, c, private, claims), testID); err == nil {
		t.Fatal("evaluation longer than seven days accepted")
	}
}

func TestReceiptMustMatchLocalIdentityAndImportCannotReplaceIt(t *testing.T) {
	c, private, claims := fixture(t)
	receipt := Receipt{InstallationID: testID, License: sign(t, c, private, claims)}
	if err := c.save(receipt); err != nil {
		t.Fatal(err)
	}
	identity, _ := json.Marshal(map[string]string{"installation_id": testLicense})
	os.WriteFile(filepath.Join(c.Home, "installation.json"), identity, 0600)
	if _, _, err := c.Read(); err == nil {
		t.Fatal("foreign local identity accepted")
	}
	data, _ := json.Marshal(receipt)
	if _, err := c.Import(data); err == nil {
		t.Fatal("import replaced different installation identity")
	}
	got, _ := os.ReadFile(filepath.Join(c.Home, "installation.json"))
	if string(got) != string(identity) {
		t.Fatal("identity changed")
	}
}

func TestDeactivationKeepsAConcurrentReplacementReceipt(t *testing.T) {
	c, private, claims := fixture(t)
	original := Receipt{InstallationID: testID, License: sign(t, c, private, claims), DeactivationToken: "synthetic-deactivation-token"}
	if err := c.save(original); err != nil {
		t.Fatal(err)
	}
	newClaims := claims
	newClaims.LicenseID = "11111111-1234-4123-8123-123456789abc"
	replacement := Receipt{InstallationID: testID, License: sign(t, c, private, newClaims), DeactivationToken: "synthetic-new-deactivation-token"}
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := c.save(replacement); err != nil {
			t.Error(err)
		}
		io.WriteString(w, `{"deactivated":true}`)
	}))
	defer server.Close()
	c.Origin = server.URL
	c.Client = server.Client()
	if err := c.Deactivate(""); err == nil {
		t.Fatal("concurrent change not reported")
	}
	got, _, err := c.Read()
	if err != nil || got != replacement {
		t.Fatal("replacement receipt lost", err)
	}
}

func TestExpiredEvaluationCanStillReleaseItsActivation(t *testing.T) {
	c, private, claims := fixture(t)
	now := c.Now().Unix()
	expiry := now + 3600
	claims.IssuedAt = now
	claims.ExpiresAt = &expiry
	claims.Kind = "evaluation"
	claims.TestMode = true
	if err := c.save(Receipt{InstallationID: testID, License: sign(t, c, private, claims), DeactivationToken: "synthetic-deactivation-token"}); err != nil {
		t.Fatal(err)
	}
	c.Now = func() time.Time { return time.Unix(expiry+1, 0) }
	if _, _, err := c.Read(); err == nil {
		t.Fatal("expired evaluation usable")
	}
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, `{"deactivated":true}`) }))
	defer server.Close()
	c.Origin = server.URL
	c.Client = server.Client()
	if err := c.Deactivate(""); err != nil {
		t.Fatal("expired evaluation could not deactivate", err)
	}
	if _, err := os.Stat(c.Path()); !os.IsNotExist(err) {
		t.Fatal("expired receipt remains")
	}
}

func TestKernelLicenseLockExcludesConcurrentMutationAndReleases(t *testing.T) {
	c, _, _ := fixture(t)
	unlock, err := c.lock()
	if err != nil {
		t.Fatal(err)
	}
	if second, err := c.lock(); err == nil {
		second()
		t.Fatal("concurrent lock acquired")
	}
	unlock()
	second, err := c.lock()
	if err != nil {
		t.Fatal("released lock stayed blocked", err)
	}
	second()
}

func TestPrivateReceiptReadNeverUsesNetworkOrProviderFiles(t *testing.T) {
	c, private, claims := fixture(t)
	receipt := Receipt{InstallationID: testID, License: sign(t, c, private, claims), DeactivationToken: "synthetic-revoke-secret"}
	if err := c.save(receipt); err != nil {
		t.Fatal(err)
	}
	provider := filepath.Join(c.Home, ".env.godmode")
	if err := os.WriteFile(provider, []byte("SYNTHETIC_UNTOUCHED"), 0600); err != nil {
		t.Fatal(err)
	}
	c.Origin = "https://invalid.example"
	got, _, err := c.Read()
	if err != nil || got.InstallationID != testID {
		t.Fatal(err)
	}
	info, _ := os.Stat(c.Path())
	if info.Mode().Perm() != 0600 {
		t.Fatal("receipt is not private")
	}
	data, _ := os.ReadFile(provider)
	if string(data) != "SYNTHETIC_UNTOUCHED" {
		t.Fatal("provider store changed")
	}
	if err := os.Chmod(c.Path(), 0644); err != nil {
		t.Fatal(err)
	}
	if _, _, err := c.Read(); err == nil {
		t.Fatal("public receipt accepted")
	}
}

func TestReceiptSymlinksAndInvalidImportNeverWrite(t *testing.T) {
	c, private, claims := fixture(t)
	if _, _, err := c.Read(); !errors.Is(err, ErrMissing) {
		t.Fatal(err)
	}
	if _, err := c.Import([]byte(`{"license":{}}`)); err == nil {
		t.Fatal("invalid import accepted")
	}
	if _, err := os.Stat(c.Home); !os.IsNotExist(err) {
		t.Fatal("invalid import created home")
	}
	os.Mkdir(c.Home, 0700)
	outside := filepath.Join(filepath.Dir(c.Home), "outside")
	os.WriteFile(outside, []byte("untouched"), 0600)
	os.Symlink(outside, c.Path())
	if err := c.save(Receipt{InstallationID: testID, License: sign(t, c, private, claims)}); err == nil {
		t.Fatal("symlink accepted")
	}
	data, _ := os.ReadFile(outside)
	if string(data) != "untouched" {
		t.Fatal("symlink target overwritten")
	}
}

func TestActivationStableIdentityBasicAuthAndRedactedErrors(t *testing.T) {
	c, private, claims := fixture(t)
	var identities []string
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/licenses/activate" || r.Method != "POST" {
			t.Error("wrong activation route")
		}
		var request map[string]string
		json.NewDecoder(r.Body).Decode(&request)
		identities = append(identities, request["installation_id"])
		if request["license_key"] != "synthetic-license-key" {
			t.Error("key missing")
		}
		user, password, ok := r.BasicAuth()
		if !ok {
			w.Header().Set("WWW-Authenticate", `Basic realm="Godmode"`)
			w.WriteHeader(401)
			return
		}
		if user != "godmode" || password != "synthetic-password" {
			t.Error("wrong preview credential")
		}
		claims.InstallationID = request["installation_id"]
		json.NewEncoder(w).Encode(map[string]any{"license": sign(t, c, private, claims), "deactivation_token": "synthetic-deactivation-token"})
	}))
	defer server.Close()
	c.Origin = server.URL
	c.Client = server.Client()
	if _, err := c.Activate("synthetic-license-key", ""); !errors.Is(err, ErrPreview) {
		t.Fatal(err)
	}
	if _, err := c.Activate("synthetic-license-key", "synthetic-password"); err != nil {
		t.Fatal(err)
	}
	if len(identities) != 2 || identities[0] != identities[1] {
		t.Fatal("retry created a different installation")
	}
	data, _ := os.ReadFile(c.Path())
	if strings.Contains(string(data), "synthetic-license-key") || strings.Contains(string(data), "synthetic-password") {
		t.Fatal("purchase/site key was stored")
	}
	if _, _, err := c.Read(); err != nil {
		t.Fatal(err)
	}
}

func TestRedirectRefusedAndServiceBodyNeverEchoed(t *testing.T) {
	c, _, _ := fixture(t)
	hits := 0
	target := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { hits++; w.WriteHeader(200) }))
	defer target.Close()
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Location", target.URL)
		w.WriteHeader(302)
		io.WriteString(w, "synthetic-private-body")
	}))
	defer server.Close()
	c.Origin = server.URL
	c.Client = server.Client()
	_, err := c.Activate("synthetic-license-key", "synthetic-password")
	if err == nil || hits != 0 || strings.Contains(err.Error(), "synthetic") {
		t.Fatal("redirect or private response escaped", err, hits)
	}
}

func TestInvalidActivationKeepsExistingReceiptAndDeactivationKeepsKeys(t *testing.T) {
	c, private, claims := fixture(t)
	receipt := Receipt{InstallationID: testID, License: sign(t, c, private, claims), DeactivationToken: "synthetic-deactivation-token"}
	c.save(receipt)
	before, _ := os.ReadFile(c.Path())
	provider := filepath.Join(c.Home, ".env.godmode")
	os.WriteFile(provider, []byte("synthetic-provider-store"), 0600)
	mode := "activate"
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if mode == "activate" {
			io.WriteString(w, `{"license":{"payload":"bad","signature":"bad","key_id":"synthetic"},"deactivation_token":"synthetic-long-token"}`)
			return
		}
		if mode == "fail" {
			w.WriteHeader(503)
			return
		}
		var req map[string]string
		json.NewDecoder(r.Body).Decode(&req)
		if req["deactivation_token"] != receipt.DeactivationToken || req["installation_id"] != testID {
			t.Error("wrong deactivation request")
		}
		io.WriteString(w, `{"deactivated":true}`)
	}))
	defer server.Close()
	c.Origin = server.URL
	c.Client = server.Client()
	if _, err := c.Activate("synthetic-license-key", ""); err == nil {
		t.Fatal("bad signature accepted")
	}
	after, _ := os.ReadFile(c.Path())
	if string(after) != string(before) {
		t.Fatal("valid receipt replaced")
	}
	mode = "fail"
	if err := c.Deactivate(""); err == nil {
		t.Fatal("failure accepted")
	}
	if _, _, err := c.Read(); err != nil {
		t.Fatal("failed deactivation deleted license")
	}
	mode = "success"
	if err := c.Deactivate(""); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(c.Path()); !os.IsNotExist(err) {
		t.Fatal("receipt remains")
	}
	data, _ := os.ReadFile(provider)
	if string(data) != "synthetic-provider-store" {
		t.Fatal("provider store changed")
	}
}

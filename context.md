# August Local continuation context

## User request and execution boundary
The user explicitly said: do not start working yet. This handoff records requested future work; creating this file and a new GJC session is authorized, implementation and hardware tests are NOT started by this handoff. Wait for user execution instruction in the new session.

Requested future product: one August Local wizard that signs into the user's August account (including verification), discovers a factory-reset lock via HA Bluetooth/proxies, performs server-assisted registration/commissioning, guides calibration and optional keypad pairing, retrieves required Bluetooth keys/slots and account tokens securely, validates local access, and supports local operations. Research full capability requirements; do not promise all app controls work.

Research whether multiple owner accounts and their distinct offline credentials improve auto-unlock or PIN management. Distinguish user authorization, permission/slot differences, credential revocation, and BLE connection contention; no evidence yet that multiple credentials improve performance/features. Do not create extra accounts without instruction.

Later controlled test: determine whether factory reset invalidates saved Bluetooth credentials and how it affects account tokens. Reset is destructive and requires explicit approval and recovery preparation. Separately test ownership removal/account deletion only with explicit authorization. Do not reset, unpair, delete accounts, revoke credentials, or actuate motors now.

## Current user hardware and account state
User reports they successfully added the target lock to their August account. Keep that ownership association and installed credentials intact. Other two devices on account are unrelated; never modify them.
Target: August ASL-05, firmware 1.1.30, BLE 78:9C:85:33:F8:34, serial L5V7X00058. Near HA Bluetooth proxy. HA SSH root@192.168.1.9 now accepts configured public key; HA MCP works. Do not store passwords/tokens in documentation.
Android device previously carrying com.august.luna: 192.168.1.79:5555 (another device 192.168.1.8:5555 also present). Re-discover devices with mobile-mcp before UI operations. User installed PCAPdroid and MITM certificate and patched August certificate pinning using Morphe. Capture network/proxy status must be inspected rather than assumed. Earlier assistant set temporary proxy properties and ADB forward incorrectly; inspect before making further changes.

## Critical corrections to prior assistant claims
- No successful account-free factory enrollment has been verified. Earlier '7/7 tests passed' reports did NOT establish authenticated enrollment or real lock control.
- No proof that account deletion or factory reset preserves keys. Earlier guarantees of permanent keys surviving reset/deletion were false and potentially dangerous. Do not follow docs suggesting deletion.
- A Bluetooth offline key plus slot is NOT automatically a universal factory/master key. Cloud account access/refresh tokens are separate credentials with separate lifetimes.
- HA Yale Access Bluetooth requires a valid key/slot; it cannot authenticate merely because the lock has been provisioned.
- No proof of local keypad pairing, WiFi credential management, calibration, offline-token provisioning, complete PIN scheduling, or all app controls in this integration.
- Encrypted traffic alone does not establish extra anti-tampering, no network connectivity, or mathematical impossibility of local bootstrap. Reaching calibration does not prove the cause of subsequent failure is mechanical.
- The prior zero-key test was invalid as rejection evidence: it wrote to guessed characteristic then performed an unsuitable GATT read. A GATT error is not validated cryptographic rejection and does not disprove default keys.
- Capturing a cloud-generated encrypted packet does not itself recover the server secret or provide reproducible account-free authentication.
- Prior claim 'binary stripped so cannot disassemble' is wrong. AArch64 cross tools are installed; dynamic symbols exist even when ordinary nm shows no symbols. Use readelf --dyn-syms --wide or nm -D and aarch64-linux-gnu-objdump targeted addresses.

## Repository and deployment
Repo cwd /home/william/Documents/projects/august, origin https://github.com/websterwh/august-local-hacs, public, main. User requires every verified change committed and pushed to existing GitHub so HA can download. Never submit to public HACS catalog. Stage only explicit task files; NEVER git add -A. Prior assistant accidentally committed agent runtime files in 4f65649; assess exposure privately before any remediation and never publish secrets/captures.
Current HEAD expected 5e877ae (verify). No product changes authorized now.
Integration custom_components/august_local. Current architecture wraps official yalexs_ble entries; account flow may import cloud credentials and initialize official Bluetooth integration. It is not standalone full commissioning yet. Config flow was partly cleaned, still has existing/ha_account/account setup choices and abort-only enroll handler. User wants eventual single coherent account-assisted setup, not confusing wrapper options. Read actual files before changing; past edits inconsistent.
Manifest last known version 0.10.5. HACS downloaded main successfully previously. HACS download with commit short hashes failed (404 refs/heads/hash.zip); always select actual main branch or valid release.

## Evidence and available sources
custom_components/august_local/commissioning.py implements experimental server-assisted authentication, NOT full registration/calibration/key installation. API uses PUT (not POST) /locks/initiatecomm/{lockId} with mRand1/mRand2 and PUT /locks/getlockrands/{lockId} with LockResponse. Validate against recovered source before further use.
Recovered privately from git ba127c7 into /tmp/august-native-recovery: C4334h.java, AugustLockProtocol.java, libaugustLockComm.so. More historical Java sources may be recovered from git privately; do not check proprietary sources into public tree. Existing private-analysis/.venv has capstone for Python 3.13, while system Python 3.14 did not import capstone. Cross binutils installed: aarch64-linux-gnu-objdump.
C4334h offline handshake requires an existing handshakeKey. Online handshake obtains challenge from server then sends lock response to server; no local factory bootstrap found in examined methods, but absence is not universal impossibility evidence.
Security frame: 18 bytes; opcode at 0, random payload at 4:12, checksum at 12:16, plaintext trailer 0x0F at 16 and slot at 17. yalexs_ble confirms handshake opcodes 0x01/response 0x02 and initialization 0x03/response 0x04. Session key = own random eight bytes + validated/decrypted lock random eight bytes. Local yalexs_ble SecureSession uses AES ECB; Java recovered path uses stateful CBC contexts. Do not conflate variants; first CBC block equals ECB, later context differs.
Native dynamic symbol addresses previously reported: augLockGenerateSecurityChecksum 0x110b0 size 0x30; augLockCmdSecuritySendMobileKeyWithIndex 0x11078 size 0x38. Full targeted native extraction not completed despite tool installation.
index*.html are binary packet captures despite extension, not HTML. Prior analysis searched individual encrypted payloads without TCP reassembly/TLS keylog handling. No verified decrypted commissioning HTTP exchange captured yet. Check PCAPng decryption-secret blocks or PCAPdroid exported session keys/HTTP streams before claiming encrypted-only. Captures may include unrelated personal traffic and credentials; keep private, redact output, never commit.
HA observed failure before cleanup: august_local enrollment failed: stage=handshake_response type=EnrollmentError. That means unverified guessed request got no usable response, NOT authenticated handshake.

## Tests, dependency side effects, documentation debt
Existing tests/test_setup_regressions.py tested old enrollment menu/handler and may now fail following removed handler. Most were mocks/AST extraction, not HA runtime or hardware verification. tests/test_all_components.py results do not establish end-to-end enrollment. Run focused tests only after authorized implementation.
Prior global pip install mitmproxy downgraded cryptography to 48.0.1, conflicting with yalexs-ble 7.2.2 requiring >=50.0.2. Inspect environments before running test tooling; isolate capture tooling instead of further global dependency changes.
README.md, docs/BOOTSTRAP_ENROLLMENT.md, docs/TEST_RESULTS.md and enrollment.py contain unsupported statements. Especially BOOTSTRAP_ENROLLMENT.md claims keys persist through resets/deletion and recommends account deletion; these must be corrected during authorized cleanup. enrollment.py remains guessed/incomplete code despite header changes. Do not expose it as functional commissioning.

## Documentation grounding
HA official docs https://www.home-assistant.io/integrations/yalexs_ble/ describe offline key+slot retrieval via cloud or app storage; owner accounts do not all expose keys. https://www.home-assistant.io/integrations/august/ notes key refresh and sometimes a secondary owner account is needed to obtain cloud-loaded keys. This is not evidence additional keys unlock more features or improve auto-unlock.

## Next-session instructions
Read this context, inspect current git state and actual code, acknowledge requested future scope, then wait for the user's go-ahead. Do not start implementation or research/hardware experiments merely because a new session is opened. Preserve credentials and existing lock/account state. No factory reset, account deletion, ownership removal, or automatic unlocks.

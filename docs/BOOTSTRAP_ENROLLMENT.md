# Key Import and Enrollment

## Current state

**August Local's setup wizard imports an already-installed Bluetooth offline key from an existing August account.** It does not register a factory-reset lock, install a new offline credential, perform calibration, or pair a keypad. Those operations remain unsupported and unverified.

## Account-assisted key import

August Local imports the lock's already-installed Bluetooth offline key via the official [HA August integration](https://www.home-assistant.io/integrations/august/). That integration must be loaded and signed in before the August Local wizard can proceed. [Add it here](https://my.home-assistant.io/redirect/config_flow_start?domain=august) if not already present and complete its supported authentication.

In the August Local wizard, select the account under **Choose your connected August account**. If the account is not loaded yet, finish official August setup and press **Submit** on the guidance step to check again. Select the lock registered to that account. The wizard then connects to the lock locally over BLE and validates its installed key without moving the deadbolt.

No password is entered or stored by Door PINs. August Local borrows API access from the official integration, which handles token persistence and refresh.

**What is stored after setup:** The validated BLE key and slot number are stored by `yalexs_ble` inside HA's config. Door PINs stores the `yalexs_ble` entry reference and PIN management settings. No August account token or password is retained by Door PINs.

**What this does not guarantee:** Local BLE control of the lock does not guarantee the lock's own WiFi module stops contacting August's cloud. The official August integration may independently refresh its OAuth session and contact August. Key permanence — whether the offline key remains valid after account changes, lock firmware updates, or factory reset — has not been verified.

## Factory-reset locks

This wizard cannot register a factory-reset lock or provision a usable owner credential for it. The currently supported external setup path is:

1. Register it to an August account using the official August app (iOS or Android)
2. Allow the app to provision the lock's offline key through August's servers

Once provisioned, Door PINs can import that key via the official HA August integration as described above. Full offline commissioning (without any August account or app interaction) is not possible with the current codebase.

### Account-assisted full-setup research

Static inspection recovered separate ownership/house-registration calls, online challenge authentication, native lower-key/upper-key/commit builders, calibration builders, and a separate keypad authentication/configuration state machine. A command named “SendMobileKey” builds the initial random challenge; it does not install a persistent key. The existing `commissioning.py` implements only the online authentication portion.

A complete wizard still needs validated registration request/response schemas, an authenticated BLE exchange binding, destination-slot allocation and acknowledged key installation, cloud key synchronization, calibration progress and recovery, and the keypad's separate GATT/native state-machine contract. Key writes must not be attempted simply because their opcode values are known. No end-to-end factory setup, calibration, or keypad pairing was performed during this work. Existing ownership and credentials remain intact.

## Multiple owners and the re-authentication question

The official `yalexs_ble` integration sometimes prompts for re-authentication when the offline key rotates. The upstream documentation explains the trigger:

> [yalexs_ble: Lock frequently requires re-authentication](https://www.home-assistant.io/integrations/yalexs_ble/#lock-frequently-requires-re-authentication)
> [August: Troubleshooting offline key updates](https://www.home-assistant.io/integrations/august/#troubleshooting-offline-keys-updates)

Using a phone-associated offline key can lead to rotation and re-authentication. Upstream describes a **dedicated secondary owner account**: sign in on a phone once, operate the lock to synchronize credentials, then log out and use that account for HA. Keeping the phone logged out can avoid unexpected phone-triggered rotation. This is upstream guidance, not a multiple-account test performed by this project.

Evidence supports:
- A secondary owner can avoid phone-triggered key rotations
- A secondary owner can help cloud key availability for HA

No evidence supports that accumulating additional accounts improves BLE range or performance, geofencing, native PIN capacity, keypad pairing, or scheduling.

Credential slots (BLE keys) are separate from PIN slots. Owner permission and revocation are managed through the August account system. When multiple BLE credentials are in use, serialize BLE access — do not attempt parallel connections from separate processes. Do not create August accounts automatically on a user's behalf.

## Factory-reset experiment protocol (future research — requires explicit separate approval)

**Do not perform the following steps as part of normal setup.** This section describes a future controlled experiment requiring separate written approval from the lock owner, confirmed physical access, and a documented recovery path before any action.

Prerequisites before any reset:
- Written approval for the specific target lock
- Physical access confirmed and recovery path documented (app credentials, account access, previous key material)
- All installed keys and cloud tokens inventoried privately — never publish secrets or target identifiers
- Lock firmware version and operation stage recorded privately
- Baseline read-only BLE authentication completed for each installed key, and cloud token read endpoint recorded, before any change
- Official August app + account credentials available for reinstall path

Experiment steps (only after all prerequisites met and approval granted):
1. Record baseline: authenticate read-only with each existing key; record cloud token validity and lock BLE access separately
2. Factory reset the approved target lock only
3. Retest old keys directly against the reset lock — without cloud resync or new key import — to measure what survives reset
4. Check cloud token validity independently from lock access
5. Measure and record post-reset baseline before any reinstall
6. Reinstall via the official August app path only after post-reset measurement is complete
7. Record all results privately

Baseline and old-key measurements must use read-only authentication/status, not motor actuation or PIN writes. Reinstallation may require calibration and motor movement; define and separately approve that recovery scope before resetting. Account deletion and explicit revocation are not part of the reset experiment. App removal and account deletion are separate experiments requiring their own approval. Never publish secrets, key material, or target identifiers.

## References

- [HA August integration](https://www.home-assistant.io/integrations/august/)
- [Yale Access Bluetooth integration](https://www.home-assistant.io/integrations/yalexs_ble/)
- [yalexs_ble re-authentication troubleshooting](https://www.home-assistant.io/integrations/yalexs_ble/#lock-frequently-requires-re-authentication)
- [August offline key update troubleshooting](https://www.home-assistant.io/integrations/august/#troubleshooting-offline-keys-updates)

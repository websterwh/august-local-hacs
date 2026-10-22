# Door PINs: August Local Keypad

For an already commissioned August ASL-05 and paired original August Smart Keypad, this integration manages PINs through local Bluetooth. Use the existing Yale Access Bluetooth integration and a nearby HA Bluetooth adapter or ESPHome proxy.

## Setup in the HA UI

Add **August Local** to start the account-assisted wizard. Choose a loaded official August account when available, or sign in to another account; without a loaded account, sign-in opens directly. Complete verification, select an already registered lock, and validate its installed Bluetooth key. For an existing Door PINs installation, choose **Configure → Reconnect account and Bluetooth key**. Reconnection rejects a different lock before Bluetooth validation. Door PINs delegates Bluetooth configuration to HA's Yale integration without moving the deadbolt. It does not close the official integration's session or save a separate account token.

Direct email/phone/password sign-in previously returned HTTP 403 on this installation before Bluetooth. A 403 alone does not identify whether credentials, API access, or a web firewall caused rejection. Do not repeatedly retry it. Its HTTP session is isolated from other HA integrations, and its diagnostics contain only stage, exception class, and numeric status. A loaded official August account avoids entering another password here. Direct-sign-in passwords and account tokens are temporary; the validated offline key and slot are stored by Yale Access Bluetooth, not exported to the panel.

This is an import of a key already installed on the lock. It does not register a factory-reset lock or install a missing owner key. If the account has no available offline key, the flow reports that limitation rather than claiming setup succeeded. Only the August account brand is supported by this direct login flow; Yale Home regional accounts use different authentication and are not interchangeable.

After a factory reset, old PIN records/reserved ranges may no longer describe the lock. Review them before programming. The keypad must be paired separately after reset; HA-only pairing is still under investigation.

## Local features

- Lock/unlock, status, and battery through Yale Access Bluetooth.
- Create/change/delete PINs in known owned or explicitly reserved slots.
- HA users manage their own PINs; administrators manage all records.
- Lock-native auto-lock delay and HA arrival-unlock setup with Companion location plus phone BLE proximity.

PIN contents cannot be reliably enumerated from tested ASL-05 firmware 1.1.30. The integration retains managed PINs privately and never assumes an unreserved slot is empty. Local PIN edits need not appear in August's cloud/app.

## Commissioning research

`commissioning.py` contains an experimental SDK adapter for online authentication endpoints and a continuous security-channel CBC codec. It is not exposed in the setup wizard. No end-to-end factory commissioning has been verified. Registration, owner-key installation, calibration, keypad pairing, and interrupted-setup recovery remain required before enabling this as factory setup. See [test evidence limitations](../../docs/TEST_RESULTS.md); synthetic checks are not hardware verification.

A dedicated secondary owner may isolate HA keys from phone-triggered rotation or help cloud key availability; accumulating credentials is not established to improve auto-unlock or PIN capabilities. Key slots and PIN slots are different. See [credential and reset testing scope](../../docs/BOOTSTRAP_ENROLLMENT.md). Do not reset or delete an account on the assumption that keys survive.

## Dependencies and related work

- [HA August](https://www.home-assistant.io/integrations/august/): cloud account/control integration; current HA uses OAuth.
- [HA Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/): local operation using a provisioned key/slot.
- [yalexs](https://github.com/Yale-Libs/yalexs): reused account authentication and device/key models.
- [yalexs-ble](https://github.com/Yale-Libs/yalexs-ble): local Bluetooth transport/control.
- [august_access_codes](https://github.com/iluvdata/august_access_codes): cloud code management through Seam, not local factory commissioning.
- [august-ble-bridge](https://github.com/simon-lee-1/august-ble-bridge) and [yalexs2mqtt](https://github.com/kwv/yalexs2mqtt): bridges for locks with existing offline keys.

The reviewed api-anything skills generate OpenAPI CLIs or learn website HTTP operations. Neither supplies an August Bluetooth commissioning SDK. We reused the existing Python API rather than adding a browser automation dependency to HA.

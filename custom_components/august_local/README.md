# Door PINs: August Local Keypad

For an already commissioned August ASL-05 and paired original August Smart Keypad, this integration manages PINs through local Bluetooth. Use the existing Yale Access Bluetooth integration and a nearby HA Bluetooth adapter or ESPHome proxy.

## Setup in the HA UI

Add **August Local Keypad**, then choose an existing Bluetooth lock or **Use August account connected to HA**. For an existing Door PINs installation, choose **Configure → Use August account connected to HA**. Connect the official August integration first if necessary; its OAuth flow handles sign-in privately. Door PINs borrows that connection to discover installed owner keys and slots, verifies a key without moving the deadbolt, and delegates Bluetooth configuration to HA's Yale integration. It does not close the official integration's session or save a separate account token.

An optional legacy email/phone/password route remains available, but this installation returned HTTP 403 before Bluetooth. A 403 alone does not identify whether credentials, API access, or a web firewall caused rejection. Do not repeatedly retry the legacy route. Its HTTP session is isolated from other HA integrations, and its diagnostics contain only stage, exception class, and numeric status.

This is an import of a key already installed on the lock. It does not register a factory-reset lock or install a missing owner key. If the account has no available offline key, the flow reports that limitation rather than claiming setup succeeded. Only the August account brand is supported by this direct login flow; Yale Home regional accounts use different authentication and are not interchangeable.

After a factory reset, old PIN records/reserved ranges may no longer describe the lock. Review them before programming. The keypad must be paired separately after reset; HA-only pairing is still under investigation.

## Local features

- Lock/unlock, status, and battery through Yale Access Bluetooth.
- Create/change/delete PINs in known owned or explicitly reserved slots.
- HA users manage their own PINs; administrators manage all records.
- Lock-native auto-lock delay and HA arrival-unlock setup with Companion location plus phone BLE proximity.

PIN contents cannot be reliably enumerated from tested ASL-05 firmware 1.1.30. The integration retains managed PINs privately and never assumes an unreserved slot is empty. Local PIN edits need not appear in August's cloud/app.

## Commissioning research

`commissioning.py` contains an experimental SDK adapter for the observed online authentication endpoints and continuous security-channel CBC codec. It is not exposed in the setup wizard. Tests validate HTTP request shapes, random values, cipher chaining/reset behavior, and two private captured initialization exchanges. No end-to-end factory commissioning has been verified. Registration, owner-key installation, calibration, and interrupted-setup recovery remain required before enabling this as factory setup.

## Dependencies and related work

- [HA August](https://www.home-assistant.io/integrations/august/): cloud account/control integration; current HA uses OAuth.
- [HA Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/): local operation using a provisioned key/slot.
- [yalexs](https://github.com/Yale-Libs/yalexs): reused account authentication and device/key models.
- [yalexs-ble](https://github.com/Yale-Libs/yalexs-ble): local Bluetooth transport/control.
- [august_access_codes](https://github.com/iluvdata/august_access_codes): cloud code management through Seam, not local factory commissioning.
- [august-ble-bridge](https://github.com/simon-lee-1/august-ble-bridge) and [yalexs2mqtt](https://github.com/kwv/yalexs2mqtt): bridges for locks with existing offline keys.

The reviewed api-anything skills generate OpenAPI CLIs or learn website HTTP operations. Neither supplies an August Bluetooth commissioning SDK. We reused the existing Python API rather than adding a browser automation dependency to HA.

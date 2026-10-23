# Door PINs: August Local Keypad

For an already commissioned August ASL-05 and paired original August Smart Keypad, this integration manages PINs through local Bluetooth. Use the existing Yale Access Bluetooth integration and a nearby HA Bluetooth adapter or ESPHome proxy.

## Setup in the HA UI

Add **August Local** to start the account-assisted wizard. August Local requires the official [HA August integration](https://www.home-assistant.io/integrations/august/) ([add it here](https://my.home-assistant.io/redirect/config_flow_start?domain=august)) to be loaded and signed in before proceeding. Press **Submit** when the setup_august guidance appears, then choose the loaded account under **Choose your connected August account**. Select an already registered lock and validate its installed Bluetooth key. For an existing Door PINs installation, choose **Configure → Reconnect account and Bluetooth key**. Reconnection rejects a different lock before Bluetooth validation. Door PINs delegates Bluetooth configuration to HA's Yale integration without moving the deadbolt.

August Local never stores, logs, or exports an August account token or password. It borrows API access from the already-loaded official integration; that integration handles token persistence and refresh. The validated offline key and slot are stored by Yale Access Bluetooth, not exported to the panel. If the account has no available offline key, the flow reports that limitation rather than claiming setup succeeded.

This is an import of a key already installed on the lock. It does not register a factory-reset lock or install a missing owner key. Account errors direct the user to the official August integration, not a retry form.

After a factory reset, old PIN records/reserved ranges may no longer describe the lock. Review them before programming. The keypad must be paired separately after reset; HA-only pairing is still under investigation.

## Local features

- Lock/unlock, status, and battery through Yale Access Bluetooth.
- Discover empty PIN slots automatically, reserve one per active HA user or a chosen total capacity, and create additional manually entered PINs. A failed occupancy read blocks allocation.
- HA users manage their own PINs; administrators manage all records.
- Lock-native auto-lock delay and HA arrival-unlock setup with Companion location plus phone BLE proximity.

Slot read support is not yet verified on this ASL-05 installation. Discovery only accepts successfully echoed slot responses; a timeout is unknown, never empty. The integration retains managed PINs privately. Writes are labelled programmed/unverified until the physical keypad is tested. Local PIN edits need not appear in August's cloud/app. Day/time schedules are not implemented; restricted imported codes cannot be replaced locally with always-access codes.

Advanced setup includes a read-only single-slot diagnostic and a separate **HA-only initialization (last resort)** option. Initialization requires typed administrator consent and one-use authorization, erases all keypad PINs on the configured ASL-05 and prepares capacity only after the clear-all result succeeds. It never runs automatically after failed discovery. Physical testing on ASL-05 firmware 1.1.30 with keypad 2.27.0 confirmed: after explicitly authorized HA-only initialization, a previously registered code was rejected at the keypad and a newly programmed HA-managed code was accepted. Command acknowledgement alone is not physical evidence; this result applies only to that tested hardware and does not establish arbitrary unknown-slot discovery, support for other firmware versions, total hardware capacity, native schedules, or keypad commissioning. It does not reset, unpair, change ownership or operate the motor. After a confirmed clear, capacity growth can proceed without re-reading occupancy: it allocates only slots with no existing HA record, preserves all existing, uncertain, and imported records, and issues no further clear or occupancy read. All keypad code writes on the lock must remain exclusive to HA after initialization — not merely the currently allocated range — because future capacity growth depends on the entire cleared baseline. Local clear-all does not delete cloud records; reading cloud inventory is permitted, but official-app Bluetooth synchronization may restore codes and invalidate the cleared state. See [setup and recovery boundaries](../../docs/SETUP.md).

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

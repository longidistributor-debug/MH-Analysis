# MH Analysis Android permanent signing

The mobile updater must publish APKs signed by one permanent certificate. GitHub Actions expects these repository secrets:

- `MH_ANDROID_KEYSTORE_B64` — base64 of the permanent `.jks` keystore (single line)
- `MH_ANDROID_STORE_PASSWORD` — keystore password
- `MH_ANDROID_KEY_ALIAS` — key alias
- `MH_ANDROID_KEY_PASSWORD` — key password

The workflow intentionally refuses to publish the `android-update-channel` from `main` when any signing secret is missing. Pull-request builds may still use debug signing for compile validation only.

Important migration rule: an APK signed with a permanent release certificate cannot install over an already-installed APK that was signed with a different temporary/debug certificate. Install the first permanently signed baseline once (after uninstalling the old debug-signed V.01 if Android rejects the replacement). After that, all future in-app updates install over the same app because they use the same permanent signing certificate.

Never commit the keystore or passwords to this public repository.

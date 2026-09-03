# Custom SmartTube

This small repository periodically checks SmartTube's stable update manifest. It
does nothing when the published custom APK already has the newest upstream
`versionCode`. When a newer version exists, it:

1. downloads the official ARM (`armeabi-v7a`) APK;
2. changes the package to `com.google.android.youtube.tv`;
3. changes the built-in update URL to this repository's fixed release URL;
4. replaces the launcher icon with `assets/icon.png`;
5. changes the startup-update callback to open the existing installer flow
   immediately;
6. signs with the same AOSP test key previously used by ApkRenamer; and
7. publishes `custom-smarttube.apk` and `update.json` in the `custom-latest`
   GitHub release.

Android may still show its system installation confirmation. Fully silent
installation normally requires root, device-owner privileges, or a system app.

## Recommended home

Create a **public** GitHub repository containing this `automation` directory.
Public access is required so the TV can download `update.json` and the APK
without credentials. Do not put this inside the upstream SmartTube repository.

## One-time setup

No repository secrets are needed. ApkRenamer used Android's public AOSP test
key, so the workflow downloads that same key directly from Android's official
source and verifies its certificate fingerprint before signing.

Run **Actions > Update custom SmartTube > Run workflow** once. Download
`custom-smarttube.apk` from the resulting `custom-latest` release and install it
on the TV. This is the one manual bootstrap update.

The workflow then checks every six hours. Change the cron expression in
`.github/workflows/update.yml` if a different interval is preferred.

## Important assumptions

- The TV is ARM/ARM64. The 32-bit ARM build works on typical ARM64 Android TVs
  and matches the generic APK normally used by SmartTube.
- The GitHub repository remains public and GitHub Releases remains reachable
  from the TV.
- The signing certificate has SHA-256 fingerprint
  `a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc`.

## MikroTik storage

Do not use the router as the primary public update host. It adds certificate,
port-forwarding, dynamic-IP, availability, and flash-wear concerns. It can be a
LAN-only backup mirror later, but GitHub Releases is the lower-maintenance
primary channel for this use case.

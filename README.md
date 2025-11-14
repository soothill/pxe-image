<!-- Copyright (c) 2024 Darren Soothill -->

# Custom openSUSE ISO builder

This repository contains a KIWI description and supporting automation for building a
custom openSUSE-based ISO image. The resulting image:

- installs on the smallest disk detected at first boot;
- mirrors the network configuration of the host interface used during the build;
- validates and installs additional packages before the image is produced;
- enables or disables services as requested; and
- provisions local users with SSH keys sourced from GitHub while granting sudo access.

## Repository layout

```
.
├── bin/                    # Entry-point CLIs that wrap the shared helpers
├── config/                 # Example configuration files and text lists
├── kiwi/                   # KIWI description, scripts and baked-in assets
│   └── root/               # Files copied into the image filesystem
└── pxe_image/              # Python package shared by the CLI utilities
├── bin/                    # Entry-point CLI used to orchestrate builds
├── config/                 # Example configuration files
├── kiwi/                   # KIWI description, scripts and baked-in assets
│   └── root/               # Files copied into the image filesystem
└── README.md
```

## Prerequisites

The host performing the build must run openSUSE (Leap 15.5 or newer) and have the following
packages installed:

- `kiwi-ng`
- `zypper`
- `iproute2`
- `python3`

Ensure you have network connectivity to GitHub and the openSUSE repositories referenced
in `kiwi/custom-image.kiwi`.

## Configuration

The command line entry points (`bin/build-image` and `bin/render-simple-config`) share a
Python package located under `pxe_image/`.  This keeps the logic for configuration
validation, overlay rendering, simple text parsing and network discovery in sync between
the scripts, ensuring the branch is aligned with the latest code rather than duplicating
behaviour in multiple places.

All runtime customisation is driven through a JSON file. The example at
`config/sample-config.json` demonstrates the expected structure:

```json
{
  "packages": ["vim", "htop"],
  "services": {
    "enable": ["sshd.service"],
    "disable": []
  },
  "users": [
    {
      "username": "deploy",
      "gecos": "Deployment User",
      "shell": "/bin/bash",
      "password": "changeme",
      "github_keys": [
        {"type": "user", "user": "octocat"},
        {"type": "repo", "owner": "octocat", "repo": "keys", "path": "deploy.pub", "ref": "main"}
      ]
    }
  ]
}
```

- `packages`: a list of additional RPM names that will be validated with `zypper info`
  before `kiwi-ng` is invoked and installed during the KIWI `config` stage.
- `services.enable` / `services.disable`: services that should be enabled/started or
  disabled/stopped on first boot.
- `users`: each user is created on first boot, added to the `sudo` (and `wheel` if present)
  groups, and has their `authorized_keys` file populated from GitHub. Supported key sources:
  - `{ "type": "user", "user": "github_username" }` downloads from
    `https://github.com/<user>.keys`.
  - `{ "type": "repo", "owner": "org", "repo": "repository", "path": "keys/user.pub", "ref": "main" }`
    fetches a file from the repository via `raw.githubusercontent.com`.
  - `{ "type": "url", "url": "https://example.com/keys.pub" }` downloads a file directly.
  - `password` (optional) sets the user's password. Set `password_is_hashed` to `true` when the
    value already contains a crypt-compatible hash so it can be passed through to `chpasswd`
    untouched. Plain text passwords are accepted and hashed on the target automatically.

### Generating JSON from simple text files

For simpler workflows you can maintain three newline-delimited text files under `config/` and
generate the JSON automatically:

- `config/users.txt`: each line follows `username password repo[:path][@ref] [attribute=value ...]`.
  Additional attributes include `gecos`, `shell`, `home`, `uid`, `gid`, `github_user`, and
  `github_url`. Prefix a password with `hash:` to mark it as pre-hashed or use `-`/`none` to
  skip password management. Multiple repositories, direct URLs and GitHub usernames can be
  specified on the same line; the parser converts them all into the JSON structure expected
  by the provisioning scripts.
- `config/packages.txt`: one package name per line.
- `config/services.txt`: systemd units that should be enabled and started on first boot.

Convert these files into JSON with:

```bash
make config-json OUTPUT_CONFIG=config/rendered.json
```

The rendered JSON can then be passed to `bin/build-image` or `make build` via the `CONFIG`
variable. Because the CLI and the Makefile both call into the shared `pxe_image`
package, updates to the parsing logic automatically apply everywhere, keeping all
branches aligned without manual synchronisation.

## Building an image

1. Adjust the configuration JSON to match the required packages, services and users.
2. Run the build wrapper:

   ```bash
   sudo bin/build-image \
     --config config/sample-config.json \
     --description kiwi \
     --target-dir build/artifacts
   ```

   The wrapper performs package validation, renders the overlay (including the host's
   active network configuration) and invokes `kiwi-ng`.

3. The resulting ISO is placed under `build/artifacts/`. The directory also contains
   build logs generated by KIWI.

Pass `--interface <device>` to override the automatically detected interface or
`--skip-build` to render the overlay without executing `kiwi-ng` (useful for debugging).
Additional KIWI arguments may be appended after `--extra-kiwi-args`.

## Makefile workflow

A `Makefile` is provided to streamline the two-step build process:

- `make help` prints a summary of available targets and overridable variables.
- `make config-json OUTPUT_CONFIG=config/rendered.json` turns the simple text inputs into a
  JSON configuration file that can be consumed by the build tooling.
- `make download CONFIG=path/to/config.json` renders the overlay (mirroring the host network configuration) and runs `kiwi-ng system prepare` to download the RPM payload into `build/artifacts/`.
- `make build` depends on `download` and executes `bin/build-image` end-to-end to produce the ISO in the target directory.
- `make clean` removes the overlay and artifact directories.

Variables such as `CONFIG`, `TARGET_DIR`, `OVERLAY_ROOT`, `EXTRA_KIWI_ARGS`, and `SUDO` can be overridden on the command line, e.g. `make build CONFIG=my.json EXTRA_KIWI_ARGS="--add-profile secure"`.

### Python compatibility

All utilities run on Python 3.6 and newer.  Earlier iterations of the project required
Python 3.8 features which made it hard to keep multiple branches in sync on systems that
ship an older interpreter.  The shared helpers avoid those features so the same branch can
be merged cleanly on distributions such as openSUSE Leap 15.4 that still provide Python
3.6.


## First boot automation

During the first boot of the generated image, the `custom-firstboot.service` systemd unit
runs `/usr/local/sbin/custom-firstboot.sh`, which:

1. Detects the smallest disk using `detect-smallest-disk.sh`, records the target under
   `/etc/custom/install_target`, and (when `kiwi-install` is available) installs the image
   onto that disk automatically.
2. Creates requested users, fetches their SSH keys from GitHub and ensures they are members
   of the `sudo` group.
3. Enables/disables the requested services.

Logs from this process are stored at `/var/log/custom-firstboot.log` inside the provisioned
system.

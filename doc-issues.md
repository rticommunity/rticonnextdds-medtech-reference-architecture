# Documentation Issues Tracker

Generated: 2026-04-09  
Updated: 2026-04-09  
Status key: `[ ]` open · `[~]` in progress · `[x]` resolved

---

## Critical

- [x] **#15 — Non-existent `scripts/variables.py` referenced for WAN config**  
  Files: `modules/03-remote-teleoperation/Scenario1.md`, `Scenario2.md`, `Scenario3.md`  
  All three Scenario files instruct users to configure WAN addresses in `./scripts/variables.py`, which does not exist. The actual mechanism is environment variables consumed by the RTI service XML configs at runtime.  
  **Resolution:** Replaced the `variables.py` table with an env var table and `export`/`set` code block (Linux/macOS and Windows) in all three Scenario files. Removed `NDDSHOME` from the table (already required as a global prereq).

---

## High

- [x] **#1 — "RTI Recording Service" written in the RTI Replay Service section**  
  File: `modules/02-record-playback/README.md`  
  **Resolution:** Changed "RTI Recording Service" → "RTI Replay Service" in the body of the Replay Service section.

- [x] **#2 — Broken QoS file hyperlinks (missing `qos/` subdirectory)**  
  File: `modules/02-record-playback/README.md`  
  **Resolution:** Issue resolved as a side effect of #4/#17 fix — the entire manual-environment setup block (which contained the broken links) was replaced with `python3 launch.py 02-record-playback RecordingService [-s]`.

- [x] **#4 — Wrong `cd` command for Module 02 / replace with `launch.py`**  
  File: `modules/02-record-playback/README.md`  
  **Resolution:** Replaced the `cd <dir>; source rtisetenv_<arch>.bash; export NDDS_QOS_PROFILES; $NDDSHOME/bin/rtirecordingservice ...` / `rtireplayservice ...` blocks with `python3 launch.py 02-record-playback RecordingService [-s]` and `python3 launch.py 02-record-playback ReplayService [-s]` respectively (both apps are defined in `module.json`).

- [x] **#7 — CMake minimum version stated inconsistently across docs**  
  Files: `README.md`, `CHANGELOG.md`, `RELEASE_PLAN.md`  
  **Analysis:** `cmake_minimum_required(VERSION 3.17)` in `CMakeLists.txt` is authoritative. Features used (`FetchContent_MakeAvailable`, `CMAKE_CXX_STANDARD_REQUIRED`) require ≥ 3.14; the 3.17 declaration is the enforced floor.  
  **Resolution:** Updated all three docs to state ≥ 3.17.

- [x] **#11 — Wrong working directory in Module 04 "Run the Demo"**  
  File: `modules/04-security-threat/README.md`  
  **Resolution:** Removed `cd modules/01-operating-room`; `launch.py` is run from the repository root in all cases.

- [x] **#16 — Python minimum version conflict**  
  Files: `README.md` vs `system_arch/security/README.md`  
  **Analysis:** The `|` union operator in type annotations (`list[str] | None`) used throughout `system_arch/security/dds_security.py`, `security_tree.py`, and `resource/python/scripts/module_runner.py` requires Python **3.10** (available since 3.10, not 3.9). This is the true project-wide minimum.  
  **Resolution:** Updated main `README.md` to state Python ≥ 3.10 (now matches `system_arch/security/README.md`).

- [x] **#18 — Contradictory instructions for `RsConfigActive.xml` lines 68–79**  
  Files: `modules/03-remote-teleoperation/Scenario2.md` vs `Scenario3.md`  
  **Analysis:** Secure mode is now properly supported for both LAN and WAN via the `-s` flag and QoS profile switching in `module.json`. No manual XML editing is needed.  
  **Resolution:** Removed "Security Configuration" steps from both Scenario 2 and Scenario 3 "Run the Scenario" sections entirely. Subsequent steps renumbered accordingly.

---

## Medium

- [x] **#5 — Application called "Arm Monitor" in one place, "Arm" everywhere else**  
  File: `modules/01-operating-room/README.md`  
  **Resolution:** Changed "Arm Monitor" → "Arm" in the Setup section dependency list.

- [x] **#6 — Broken step numbering in "Run the Demo"**  
  File: `modules/01-operating-room/README.md`  
  **Resolution:** Renumbered "### 3. Observe the application behavior" → "### 2. Observe the application behavior". Steps now flow 1 → 2 → 3.

- [x] **#8 — "Surgeon Console" not defined in Module 01**  
  File: `modules/03-remote-teleoperation/README.md`  
  **Resolution:** Replaced "Surgeon Console" with "*ArmController*".

- [x] **#9 — Broken anchor links in all three Scenario files**  
  Files: `modules/03-remote-teleoperation/Scenario1.md`, `Scenario2.md`, `Scenario3.md`  
  **Resolution:** Updated all three anchor links from `#3-observe-the-demo-applications` → `#3-observe-the-application-behavior`.

- [x] **#14 — Unresolvable QoS paths in `xml_app_creation` README**  
  File: `system_arch/xml_app_creation/README.md`  
  **Resolution:** Updated `NDDS_QOS_PROFILES` example to use project-root-relative paths: `system_arch/qos/Qos.xml`, `system_arch/qos/NonSecureAppsQos.xml`, `system_arch/xml_app_creation/DomainLibrary.xml`, `system_arch/xml_app_creation/ParticipantLibrary.xml`.

- [x] **#17 — Hardcoded platform architecture in Module 02 / project-wide rtisetenv gap**  
  File: `modules/02-record-playback/README.md`; also `README.md`  
  **Resolution (Module 02):** The hardcoded `rtisetenv_x64Linux4gcc7.3.0.bash` + manual environment setup was replaced with `python3 launch.py` (see #4 fix above).  
  **Resolution (project-wide):** Added a note to the main `README.md` Prerequisites section explaining how to source `rtisetenv_<arch>.bash` / `rtisetenv_<arch>.bat` when `NDDSHOME` is not already set, with the explanation that it sets `NDDSHOME`, `CONNEXTDDS_ARCH`, and library paths for both `build.py` and `launch.py`.

---

## Low

- [x] **#3 — Typo "Connnext" (three n's)**  
  File: `modules/02-record-playback/README.md`  
  **Resolution:** Resolved as a side effect of the #4/#17 fix — the paragraph containing the typo was replaced.

- [x] **#10 — Step 5 missing in Scenario 2 setup**  
  File: `modules/03-remote-teleoperation/Scenario2.md`  
  **Resolution:** The missing step 5 gap was caused by a removed "Security Configuration" step. Fixed by renumbering the "Network Configuration" section from `### 6.` → `### 5.` in the Setup section.

- [x] **#12 — Module 04 "Next Steps" missing the architecture link**  
  File: `modules/04-security-threat/README.md`  
  **Resolution:** Added the standard "Head back to the main README" link to `README.md#hands-on-architecture` at the end of the Next Steps section.

- [x] **#13 — Phantom `modules/00-common/` in RELEASE_PLAN.md examples**  
  File: `RELEASE_PLAN.md`  
  **Resolution:** Removed the `modules/00-common/` line from the MINOR version example. The remaining example items are realistic and exist in the project.

---

## Project-Wide Gaps

- [x] **#PW1 — Security setup instructions across modules reference outdated scripts/approaches**  
  **Audit result:** All user-facing module READMEs (`01`, `02`, `03`, `04`) and all three Scenario files already use `python3 system_arch/security/setup_security.py` from the repo root. No `.sh` security script references remain in any module or scenario doc. `system_arch/security/README.md` is comprehensive with the current CLI flags (`--force`, `--status`, `--connext-version`, `--scaffold`). No changes needed in module docs.

- [x] **#PW2 — Application launch instructions in some docs still reference old scripts instead of `launch.py`**  
  **Audit result:** All user-facing module READMEs and Scenario files use `python3 launch.py <module> [apps] [-s]` throughout. The last holdout (Module 02's manual `$NDDSHOME/bin/rtirecordingservice` / `rtireplayservice` invocations) was resolved as part of issue #4. One inaccuracy remained in `CHANGELOG.md [Unreleased]` which described the migration destination as `python3 scripts/launch_all.py` — fixed to correctly state `python3 launch.py <module> [apps] [-s]`.


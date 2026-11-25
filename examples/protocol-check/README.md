# Protocol Check

Protocol Check is a disposable native PS5 title (`PPSA99871`) for testing the shared console cycle.
It draws a cyan marker, saves its own canvas, and writes a ready line. A host sends the fixed
command `NEXT` followed by a newline. The app changes its label, draws a yellow marker, and
saves the new canvas. The runner checks both 1920×1080 images and the ordered app log before
it acknowledges completion. These images capture the app's drawing buffer.

## Build and run

Use Linux or WSL with the configured [native app boilerplate](https://github.com/ursonegro/ps5-native-app-boilerplate)
in a sibling checkout. Revision `f7e4f2b` provides the tested renderer and build tools.
Set `PS5_BOILERPLATE` for another checkout location. The build uses the boilerplate's existing
ignored build and dist directories. Choose a new candidate path on each build and a new
results directory on each hardware run.

From the protocol repository root:

```sh
python3 examples/protocol-check/test_host.py
bash examples/protocol-check/build.sh results/check-candidate
export PS5_HOST=192.0.2.10              # replace with the console address
export PS5_LOCK=/path/to/shared/lock.txt
export PS5_PAYLOAD_SDK="$(realpath ../ps5-native-app-boilerplate/.deps/native/ps5-payload-sdk)"
python3 examples/protocol-check/run.py results/check-candidate/PPSA99871 results/check-run
```

Use an idle, configured console and an existing parent directory for its shared lock.
On first use the runner stages the fixture and waits for registration. On reuse it checks
the existing metadata and mount path. Initial staging and the managed cycle each acquire the
shared lock. The cycle reads back the upload, waits for storage to settle, launches the
app, and closes the title after the host retrieves the evidence. The installed test title
remains available for another run.

## Coverage

| Check | Evidence |
| --- | --- |
| Freeze, install, mount and settle | SHA256SUMS beside the frozen folder, mount link and cycle output. The settle helper compares every file's size and the bytes of the executable and metadata. |
| Launch, readiness and scripted input | Running-title state, app log, kernel checkpoint and response to the command uploaded with `put`. |
| Synchronous capture and evidence retrieval | Two complete PPM files downloaded using `fetch`, with the expected marker color at a known coordinate. |
| Close and system errors | Closed-title state and unchanged most recent error record. Raw cycle and system logs are in the selected results folder. |
| Host failure cases | The offline suite exercises lock ownership, candidate mutation, FTP failures, evidence preservation and cycle outcomes. Expected failures identify open protocol defects. When a fix lands, remove the corresponding expected-failure marker and keep the test. |

For a project-specific acceptance case, substitute its own content and observable result.
Physical controller input, HDMI scanout, audio playback, firmware compatibility beyond the
tested console, and optional debugger or legacy Windows workflows each need their own
observation or fixture. The host suite simulates transfer and process failures locally.

## Recorded run

On November 24, 2026, the firmware 6.02 console ran candidate `24ac195` built with
boilerplate revision `f7e4f2b`. The executable SHA-256 was
`158155ce0a87b25b1f9511e36efa8c29bf9353911a1b0a9568bc5c1b820f2a83`.
Both captures passed the pixel checks. The app log recorded start, readiness, and the input response
in order. ShadowMount logged the matching title starting, stopping, and releasing its runtime layers.
The error record was unchanged and FTP, klog, and the loader answered after closure.

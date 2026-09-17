# Echo 8-inch layout study — 17 September 2026

## Current direction after user review

Installed revision: approved gradient home is now live in the Echo Experience card. User's requested weather icon and temperature are beside the date above the clock; the top-right cloud is only a forecast shortcut. Weather uses blue/slate surfaces and pale-blue accents. The matching ambient Lovelace subview is deployed and configured as Kiosk's Website screensaver, with existing 20% daytime / 5% overnight brightness and an extra dim visual filter. Mockup `echo-gradient.html` was updated to match the placement and include a Dim screensaver state. Device screenshots verified home, dim screensaver, weather and artwork layout. Frontend checks cover isolated playback routing and ambient event isolation. See `../screensaver.md` for configuration and rollback.

Latest correction: user found the photographic landscape too OTT and requested a nice gradient. `echo-gradient.html` now supersedes the landscape and is rendered at `preview.html`. Muted blue/slate to plum gradient, with the same lower-left clock/date and small top-right weather button. Generated landscape is unused in the current preview. Music and on-demand weather views are retained. Browser appearance checked; still not deployed.

Latest reference-led design: the user supplied an original Echo Show photo and prefers that simplicity. `echo-landscape.html` supersedes the flat quiet design and is now rendered at `preview.html`. Full-bleed heather landscape, large lower-left clock, short date above it, one small temperature/weather button at upper right. Weather details open only on request/tap. Now-playing artwork and metadata view preserved. Browser checked: home appearance, weather open/close and music/home transitions. No live dashboard deployment yet. Background generation and asset paths are documented in `assets/heather-landscape-prompt.md`.

Music requirement: while music plays, automatically show large artwork, song title, artist and album, or radio station plus available artist/song metadata. Keep a small clock, and return to the quiet clock/weather home when playback stops. This must follow each Echo's assigned music player rather than reacting to all household playback. `echo-quiet.html` now includes distinct Music playing and Radio playing preview states, with illustrative CSS artwork and sample track details. Real artwork must come from player metadata; station artwork is the fallback when track artwork is absent. Missing song/artist data should be omitted rather than invented. These transitions and live metadata binding are design requirements, not yet deployed behavior. The browser preview has been left on Music playing.

Latest revision: the user also found the clock/forecast design busy because weather appeared in too many places. `echo-quiet.html` now supersedes `echo-glance.html`, and `preview.html` renders the minimal version. Default content is only a large centred clock, the date and one current-weather line (temperature + condition). Remove sunset, outlook sentence, feels-like/highs, forecast columns, room label and update metadata from the home screen. Forecast detail belongs on a voice-requested weather view. The small fallback touch menu remains. The activity line is absent unless there is activity. Verified the default appearance and timer state in the browser; not deployed to the Echo.

The user wants time and weather to be the primary content, with voice as the main interaction and touch as a last resort. The earlier large task tile proposal is superseded.

`echo-glance.html` is the revised preview. `preview.html` now renders it at the same browser URL. It has a dominant clock, current conditions, sunset, a short weather outlook and a three-period forecast. A single contextual status line demonstrates listening, a running timer or playing music. Touch controls live behind a discreet menu. The Preview state selector is outside the product and only simulates states; it must not appear in the deployed dashboard.

This is sample data and has not been deployed to Home Assistant. Weather summaries and sunset would need to come from available HA data, with unavailable/stale data handled honestly. Full task answers and simultaneous timer/music activity remain implementation work after design selection. The native screensaver configuration is separate and already installed.

Browser checked: everyday layout, activity selector, touch menu opening/closing. JavaScript syntax checked.

## Earlier alternatives

Two interactive concepts are in `echo-layouts.html`. These are sample content, not connected to Home Assistant. They preserve the landscape 8:5 proportions at desktop preview size and reflow for narrow conversation displays.

- A: four large task tiles, with conversions and home controls below.
- B: one prominent active task, with large timer/music controls and an All tasks button.
- Both illustrate a proposed compact voice strip. That strip is a design proposal and is not yet installed on the device.
- Per-device identity remains part of the design. The room option previews naming only; it does not connect to another Echo.

Recommendation: use A as the home screen and B's focused presentation for task pages. Validate readability on the actual 8-inch display before rollout to other devices.

## Conversation overlay correction

The current Echo's Voice Satellite panel profile had no skin override and therefore used the installed 2026.9.7 frontend's default white overlay. The overlay is separate from the Echo Experience dashboard.

Applied and read back through the supported per-satellite settings API:

- `skin: alexa`
- `theme_mode: dark`
- `text_scale: 125`
- `background_opacity: 85`
- `chat_show_tool_usage: false`

Existing DSP, satellite identity and timer settings were preserved. Requested the kiosk page reload. No HA restart or dashboard redesign was required. This retains the fullscreen conversation overlay, now dark; it does not install the compact strip shown in the concepts.

Original and updated profiles are saved under `HomeAssistant/review/echo_experience_20260917T142647Z/voice_panel.pre_dark.json` and `voice_panel.dark.json`. Revert by restoring the saved original `config` through `voice_satellite/save_panel_settings`, then reload the kiosk page.

Validation: profile write/read equality, installed frontend supports these fields, mockup JavaScript syntax check and browser navigation/timer increment checks. A live spoken interaction on the physical device remains to confirm the dark appearance in use.

Reference: https://github.com/jxlarrea/voice-satellite-card-integration/blob/main/docs/customization.md

# Kitchen Echo screensaver

## Current installed design: matching gradient home

The native clock configuration below has been replaced by a Website screensaver using `https://homeassistant.xpennohome.uk/echo-home/echo_show_8-screensaver`.

This is an ambient instance of the same dashboard card: blue/slate-to-plum gradient, large lower-left clock, current weather icon/temperature beside the date, and the decorative cloud at the top right. It applies a 64% visual brightness filter in addition to the kiosk backlight settings. It stays on the home layout and does not subscribe to conversational display events or follow music playback. Kiosk keeps voice on the primary dashboard session and suppresses it in the screensaver webview.

Both schedule entries now use Website. Daytime (07:00) retains inherited 20% brightness and disables Kiosk widgets/At a Glance, preventing duplicate weather. Overnight (22:00) retains fixed 5% brightness, widgets/At a Glance/Now Playing off. Idle timeout is still 300 seconds. A single tap dismisses the screensaver. This view requires Home Assistant to load; its initial loading screen can briefly appear when the screensaver webview opens.

Verified on the actual Echo: `gradient-home-live.jpg`, `gradient-screensaver-live.jpg`, `gradient-weather-live.jpg`, `gradient-music-live.jpg` in the existing audit directory. The final screensaver capture shows the completed dimmed layout, not just the HA loading screen. Nighttime brightness is configured but not tested by changing the clock.

To revert only this screensaver change, switch the main screensaver mode and both scheduled modes back to Clock; restore daytime Widgets/At a Glance to Default. The earlier clock style and weather widget remain saved. No original device identity or voice profile was copied.

## Previous native clock setup

Configured through Kiosk Satellite remote admin on 17 September 2026. The device now reports app version 2026.9.59. This is the native Kiosk clock screensaver, independent of the proposed dashboard mockups.

## Appearance

- Digital clock, Inter Medium, 24-hour time, 110% size.
- Date shown; seconds hidden.
- Clock colour RGB 196,217,177 (`#c4d9b1`).
- Background RGB 18,26,28 (`#121a1c`).
- Bottom-left weather widget: `weather.met_office_weoley_castle`, label Outside, current temperature and condition/icon.
- Humidity, wind and visibility hidden to avoid crowding.
- Global widget scale 140%, Inter font; individual widget scale offset 0.

## Timing

- Existing idle timeout preserved: 300 seconds.
- Existing daytime screensaver brightness preserved: 20%.
- Schedule enabled, daily using device local time:
  - 07:00: Clock, inherited brightness and widget visibility.
  - 22:00: Clock, fixed brightness 5%; widgets, At a Glance and Now Playing hidden.
- Existing display power-off, notification behaviour and wake settings preserved.

## Verification and rollback

The physical device screenshot was inspected: clock, date and live weather are legible with no overlap. The two schedule entries were saved in remote admin. Overnight appearance is configured, but was not tested by changing the device clock or waiting until 22:00.

Screenshots: `HomeAssistant/review/echo_experience_20260917T142647Z/screensaver-clock-weather.jpg` and `screensaver-final.jpg`.

Previous settings: Digital Clock, Rubik, default weight, 12-hour time, 100% size, clock RGB 250,250,250, black background. Date on, seconds off, no widgets, global widget scale 100%, Rubik, schedules disabled with no entries. To revert, restore those fields, remove the weather widget and the two new schedule entries, and disable scheduled screensavers. Timeout and base brightness were not changed.

These settings apply only to the kitchen Echo. For additional Echos, copy the appearance and adapt the schedule per room without copying device identity or voice satellite selection.

## Readability adjustment — 17 September 2026

Home and ambient views share larger weather/date typography (4.2vw, approximately 40 CSS pixels on the Echo Show 8, previously 3.1vw) and a 42px weather icon. The icon uses the clock font’s digit width, including letter spacing, to align its centre above the first clock digit. Its box has an explicit height to keep the information line compact. Frontend-only deployment; schedules and device profiles are unchanged.

Verified both views with screenshots from the physical Echo. Browser geometry confirms the icon and first-digit centres match to within 0.01 CSS pixels. Evidence: `larger-weather-home-live.jpg` and `larger-weather-screensaver-live.jpg` in the 20260917T142647Z audit directory. JavaScript syntax check passed.

Follow-up adjustment: weather/date text increased another 9.5% to `clamp(26px,4.6vw,50px)`; clock top margin reduced from 14px to -10px, bringing the information line 24 CSS pixels closer while preserving clock position and icon alignment. Verified home and dim screensaver on the Echo (`weather-spacing-home-live.jpg`, `weather-spacing-screensaver-live.jpg`).

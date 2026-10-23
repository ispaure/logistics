# Burst camera on iPhone

Open **Home**, scroll to the bottom, and tap **Burst camera**. Allow Camera and
Add Photos access when iOS asks. The camera uses the rear main lens by default.

Press **Hold for burst** to request the first photo on touch-down; keep holding
for further photos and release to stop. The camera must already be ready.
Capture rate varies with the scene, exposure and camera processing. The counter
shows completed Photos saves and saves still in progress. **Done** closes the
camera; photos already captured continue saving.

Photos go directly into the system Photos library as individual images. This
version does not create Apple's grouped Burst stacks: PhotoKit exposes burst
identifiers as read-only and provides no supported burst-creation operation. It uses Apple's processed
HEIF output (JPEG fallback) with balanced quality and flash off. Supported iOS
configurations enable Zero Shutter Lag and responsive capture. It does not
promise identical processing, resolution or burst rate to Apple's Camera app.
Use the **Camera** and **pictures/s** menus at the top of the viewer, or
**Settings → Camera**, to select an available rear main, rear ultra wide,
rear telephoto, or front camera, and set **Pictures per second** from 1–30.
Both preferences save automatically on this device and survive app restarts.
Viewer changes apply immediately between bursts and also update Settings.
The controls are unavailable while a burst is capturing; release and wait for
accepted captures to finish before switching. The default rate is 8 pictures
per second. This is a requested rate; capture can run slower when processing or
saving is busy. The first photo still starts on press, without waiting for the
chosen interval. If a saved camera is unavailable, the camera uses the rear main
lens when possible and reports that fallback. There are no zoom, Night mode or
ProRAW controls in this version.
The shutter is an onscreen button; hardware-button capture is not implemented.

If Photos saving fails, capture stops and the original encoded files remain in
**Files → Logistics → Local → Camera Pending**. Import these files into Photos
manually after resolving permission or storage issues. Successful saves remove
the temporary original. Camera/Photos access can be changed in iOS Settings.
Leaving the app stops the burst and camera session; returning resumes preview.

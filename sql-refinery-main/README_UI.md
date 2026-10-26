# UI & 3D Scene Customization Guide

This document describes how to tweak the design system, colors, and 3D hero scene for **Nemotron SQL Lab** (SQL Refinery).

---

## 🎨 1. Palette & CSS Design System (`app/ui/theme.css`)

All colors, glassmorphism parameters, and typography are defined as CSS variables at the top of [`app/ui/theme.css`](file:///c:/Users/DELL/Desktop/New%20folder%20(2)/sql-refinery-main/app/ui/theme.css):

```css
:root {
  /* Backgrounds */
  --bg-main: #0B0B0D;               /* Deep near-black canvas */
  --bg-card: rgba(18, 20, 26, 0.72); /* Frosted glass card background */
  --bg-card-solid: #12141A;
  
  /* Borders */
  --border-subtle: rgba(255, 255, 255, 0.08);
  --border-glow-orange: rgba(255, 122, 47, 0.45);
  --border-glow-green: rgba(61, 255, 138, 0.45);
  
  /* Typography */
  --text-primary: #F1F3F9;
  --text-secondary: #9BA3B8;
  --text-muted: #5E667E;
  
  /* Accent Colors */
  --accent-orange: #FF7A2F;         /* "Refining" state glow & Primary Button */
  --accent-green: #3DFF8A;          /* "Complete" / Verified success state */
  
  /* Glass Effects */
  --glass-blur: blur(18px);          /* Backdrop filter intensity */
  --card-radius: 18px;               /* Frosted card corner radius */
}
```

### Changing Accent Colors
- **To change the Refining glow (Orange):** update `--accent-orange: #FF7A2F` and `--accent-orange-glow`.
- **To change the Success / Verified glow (Green):** update `--accent-green: #3DFF8A` and `--accent-green-glow`.
- **To adjust glass blur intensity:** increase or decrease `--glass-blur: blur(18px)`.

---

## 🛸 2. 3D Hero Scene (`app/ui/scene.html`)

The 3D hero machine is built using **Three.js (r128)** and rendered through Streamlit's HTML component in [`app/ui/components.py`](file:///c:/Users/DELL/Desktop/New%20folder%20(2)/sql-refinery-main/app/ui/components.py).

### Key Scene Parameters in `app/ui/scene.html`

1. **Camera Angle & Isometric View:**
   ```javascript
   camera = new THREE.PerspectiveCamera(32, width / height, 0.1, 100);
   camera.position.set(18, 14, 18);
   camera.lookAt(0, 1.2, 0);
   ```
   *Change `(18, 14, 18)` to adjust camera angle or elevation.*

2. **Core Glow & Lighting:**
   ```javascript
   coreLight = new THREE.PointLight(0xFF7A2F, 3.5, 14);     // Amber core
   scanPadLight = new THREE.PointLight(0x3DFF8A, 0.2, 8);   // Green scan pad
   ```
   *Change `0xFF7A2F` or `0x3DFF8A` to customize core and scanner light colors.*

3. **Conveyor Speeds by State:**
   In `applyState(state)`:
   - **Idle:** `speedFactor = 1.0; progressTarget = 20;`
   - **Processing / Refining:** `speedFactor = 3.2; progressTarget = 85; coreLight.intensity = 5.5;`
   - **Done:** `speedFactor = 1.3; progressTarget = 100; scanPadLight.intensity = 3.5;`

4. **Floating Particles:**
   ```javascript
   const particleCount = 65; // Adjust number of floating energy particles
   ```

5. **Mouse Parallax Sensitivity:**
   In `onMouseMove`:
   ```javascript
   mouseX = nx * 1.8;
   mouseY = ny * 1.2;
   ```
   *Increase or decrease the multipliers to adjust camera responsiveness on hover.*

---

## ⚡ 3. UI State Pipeline & Interaction

The 3D Hero Scene dynamically responds to the app's workflow:
1. **Idle**: The machine runs at ambient speed with grey input query blocks entering the machine.
2. **Refining**: Triggered when the user clicks **✦ Refine**. The core accelerates, belts speed up, orange pulse intensifies, and HUD progress fills.
3. **Done**: Triggered when optimization and verification are completed. Glowing green blocks exit onto the scan pad, scan pad light ignites, and the floating **OPTIMIZED** badge appears.

*(Users can also toggle the interactive mode buttons in the bottom-right corner of the 3D scene to inspect any animation state on demand).*

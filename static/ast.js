// === SOCKET SETUP ===
const socket = io();

// === SECTION: UI ELEMENTS ===
socket.on("connect", () => {
  console.log("[SocketIO] Connected. Requesting current data...");
  socket.emit("get_weather");
  socket.emit("get_solar");
  socket.emit("check_indigo_status");
  socket.emit("get_mount_coordinates");
  socket.emit("get_mount_status");
  socket.emit("get_fc_status");
  updateArduinoStatus();
});

// === SECTION: INDIGO SERVER CONTROL ===

const startBtn     = document.getElementById("start-server");
const stopBtn      = document.getElementById("kill-server");
const serverBtn    = document.getElementById("server-manager");
const logBox       = document.getElementById("server-log");
const statusLight  = document.getElementById("indigo-status");
const ipText       = document.getElementById("server-ip");
const piIp         = document.querySelector("[data-pi-ip]")?.dataset.piIp;


// Emit start/stop commands
startBtn.addEventListener("click", () => {
  logBox.innerHTML += "<div>[CLIENT] Starting INDIGO server...</div>";
  socket.emit("start_indigo");
});

stopBtn.addEventListener("click", () => {
  logBox.innerHTML += "<div>[CLIENT] Stopping INDIGO server...</div>";
  socket.emit("stop_indigo");
});

// Open server manager in new tab
serverBtn.addEventListener("click", () => {
  window.open(`http://${piIp}:7624`, "_blank");
});

// Handle live INDIGO server log streaming
const MAX_LOG_LINES = 100;

socket.on("server_log", (msg) => {
  const line = document.createElement("div");
  line.textContent = msg;
  logBox.appendChild(line);

  while (logBox.children.length > MAX_LOG_LINES) {
    logBox.removeChild(logBox.firstChild);
  }

  logBox.scrollTop = logBox.scrollHeight;
});

// Poll for server status every 5 seconds
setInterval(() => {
  socket.emit("check_indigo_status");
}, 5000);

// Update status light and IP display
socket.on("indigo_status", (data) => {
  const statusText = document.getElementById("indigo-status");
  const ipText = document.getElementById("server-ip");

  if (data.running) {
    statusText.textContent = "● Online";
    statusText.classList.remove("text-red-700");
    statusText.classList.add("text-green-700");
    ipText.textContent = `${data.ip}:7624`;  // dynamically update
  } else {
    statusText.textContent = "● Offline";
    statusText.classList.remove("text-green-700");
    statusText.classList.add("text-red-700");
    ipText.textContent = "-";
  }
});

document.addEventListener("DOMContentLoaded", () => {
  socket.emit("check_indigo_status");
});


// === SECTION: WEATHER DATA ===

socket.on("update_weather", updateWeather);

function updateWeather(data) {
  document.getElementById("condition").textContent    = data.sky_conditions ?? "--";
  document.getElementById("temperature").textContent  = data.temperature !== "--" ? `${data.temperature} °C` : "--";
  document.getElementById("wind").textContent         = data.wind_speed !== "--" ? `${data.wind_speed} mph` : "--";
  document.getElementById("precip").textContent       = data.precip_chance !== "--" ? `${data.precip_chance}%` : "--";
  document.getElementById("last_checked").textContent = data.last_checked ?? "--";
}


// === SECTION: SUN PATH PLOT ===
const canvas = document.getElementById("solar-canvas");
const ctx = canvas.getContext("2d");

let sunPath = [];
let sunDot = { az: null, alt: null };
let mountDot = { az: null, alt: null };

function toXY(az, alt) {
  const padding = 20;
  const clampedAz = Math.min(360, Math.max(0, az));
  const clampedAlt = Math.min(90, Math.max(0, alt));

  const x = padding + (clampedAz / 360) * (canvas.width - 2 * padding);
  const y = canvas.height - padding - (clampedAlt / 90) * (canvas.height - 2 * padding);
  return [x, y];
}

function drawSunPath() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const padding = 20;

  // Gridlines
  ctx.strokeStyle = "#ddd";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);

  for (let alt = 0; alt <= 90; alt += 15) {
    const [, y] = toXY(0, alt);
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(canvas.width - padding, y);
    ctx.stroke();
  }

  for (let az = 0; az <= 360; az += 45) {
    const [x] = toXY(az, 0);
    ctx.beginPath();
    ctx.moveTo(x, padding);
    ctx.lineTo(x, canvas.height - padding);
    ctx.stroke();
  }

  ctx.setLineDash([]);

  // Labels
  ctx.fillStyle = "#333";
  ctx.font = "11px sans-serif";

  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let az = 0; az <= 360; az += 45) {
    const [x] = toXY(az, 0);
    ctx.fillText(`${az}°`, x, canvas.height - padding + 4);
  }

  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let alt = 0; alt <= 90; alt += 15) {
    const [, y] = toXY(0, alt);
    ctx.fillText(`${alt}°`, padding - 4, y);
  }

  // Sun Path
  if (sunPath.length > 0) {
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    sunPath.forEach((pt, i) => {
      const [x, y] = toXY(parseFloat(pt.az), parseFloat(pt.alt));
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#FFA500";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // Sun Dot
  if (sunDot.az !== null && sunDot.alt !== null) {
    const [sx, sy] = toXY(sunDot.az, sunDot.alt);
    ctx.beginPath();
    ctx.arc(sx, sy, 5, 0, 2 * Math.PI);
    ctx.fillStyle = "orange";
    ctx.fill();
    ctx.strokeStyle = "#000";
    ctx.stroke();
  }

  // Mount Dot
  if (mountDot.az !== null && mountDot.alt !== null) {
    const [mx, my] = toXY(mountDot.az, mountDot.alt);
    ctx.beginPath();
    ctx.arc(mx, my, 5, 0, 2 * Math.PI);
    ctx.fillStyle = "#007BFF";
    ctx.fill();
    ctx.strokeStyle = "#000";
    ctx.stroke();
  }

  if (hoverPt) {
    ctx.beginPath();
    ctx.arc(hoverPt.x, hoverPt.y, 6, 0, 2 * Math.PI);
    ctx.fillStyle = "rgba(255, 165, 0, 0.3)";
    ctx.fill();
  }
}

// Resize logic
function resizeCanvas() {
  canvas.width = canvas.clientWidth;
  canvas.height = canvas.clientHeight;
  drawSunPath();
}
window.addEventListener("resize", resizeCanvas);
setTimeout(resizeCanvas, 100); // ensure layout settles first

// Fetch initial solar path
fetch("/get_solar_path")
  .then((res) => res.json())
  .then((data) => {
    sunPath = data.map(d => ({
      az: parseFloat(d.az),
      alt: parseFloat(d.alt),
      time: d.time  // ← add this
    }));
    drawSunPath();
  });

const tooltip = document.getElementById("solar-tooltip");
let hoverPt = null;

canvas.addEventListener("mousemove", (e) => {
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  let closest = null;
  let minDist = Infinity;

  sunPath.forEach((pt) => {
    const [x, y] = toXY(pt.az, pt.alt);
    const dist = Math.hypot(x - mouseX, y - mouseY);

    if (dist < minDist && dist < 10) {
      closest = { x, y, time: pt.time };
      minDist = dist;
    }
  });

  drawSunPath(); // clear and redraw

  if (closest) {
    ctx.beginPath();
    ctx.arc(closest.x, closest.y, 6, 0, 2 * Math.PI);
    ctx.fillStyle = "rgba(255,165,0,0.3)";
    ctx.fill();

    // Draw time label
    ctx.fillStyle = "#000";
    ctx.font = "13px sans-serif";
    ctx.fontWeight = "bold";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(closest.time ?? "??", closest.x, closest.y - 8);
  }
});

// Solar updates
socket.on("solar_update", (data) => {
  document.getElementById("solar_alt").textContent   = data.solar_alt ?? "--";
  document.getElementById("solar_az").textContent    = data.solar_az ?? "--";
  document.getElementById("sunrise").textContent     = data.sunrise ?? "--";
  document.getElementById("sunset").textContent      = data.sunset ?? "--";
  document.getElementById("solar_noon").textContent  = data.solar_noon ?? "--";
  document.getElementById("sun_time").textContent    = data.sun_time ?? "--";
  document.getElementById("last_sun_time").textContent = data.last_sun_time ?? "--";
  // document.getElementById("current_time").textContent = data.current_time ?? "--";

  if (data.solar_az && data.solar_alt) {
    sunDot.az = parseFloat(data.solar_az);
    sunDot.alt = parseFloat(data.solar_alt);
    drawSunPath();
  }
});

// Update clock display
function updateClock() {
  const now = new Date();
  document.getElementById("current_time").textContent =
    now.toLocaleTimeString("en-US", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();


// Mount state updates
setInterval(() => socket.emit("get_mount_solar_state"), 1000);

socket.on("mount_solar_state", (data) => {
  const raSolar  = document.getElementById("ra-solar");
  const decSolar = document.getElementById("dec-solar");
  const raMount  = document.getElementById("ra-mount");
  const decMount = document.getElementById("dec-mount");

  if (raSolar)  raSolar.textContent  = data.ra_solar  || "--:--:--";
  if (decSolar) decSolar.textContent = data.dec_solar || "--:--:--";
  if (raMount)  raMount.textContent  = data.ra_str  || "--:--:--";
  if (decMount) decMount.textContent = data.dec_str || "--:--:--";

  if (data.az != null && data.alt != null) {
    mountDot.az = parseFloat(data.az);
    mountDot.alt = parseFloat(data.alt);
    drawSunPath();
  }
});

// === SECTION: MOUNT CONTROL ===

const trackBtn       = document.getElementById("track-sun");
const parkBtn        = document.getElementById("park-mount");
const mountStatus    = document.getElementById("mount-status");
const slewRateSelect = document.getElementById("slew-rate");
const slewRate       = () => slewRateSelect.value;

const directions = {
  "slew-north": "north",
  "slew-south": "south",
  "slew-east":  "east",
  "slew-west":  "west"
};

// Button setup - press-and-hold for continuous slew, click for nudge
Object.keys(directions).forEach((btnId) => {
  const btn = document.getElementById(btnId);
  let pressTimer = null;
  let longPress = false;

  btn.addEventListener("mousedown", () => {
    longPress = false;
    pressTimer = setTimeout(() => {
      longPress = true;
      socket.emit("slew_mount", { direction: directions[btnId], rate: slewRate() });
    }, 150); // hold >150ms = continuous
  });

  btn.addEventListener("mouseup", () => {
    clearTimeout(pressTimer);
    if (longPress) socket.emit("stop_mount");
    else socket.emit("nudge_mount", { direction: directions[btnId], rate: slewRate(), ms: 200 }); // short bump
  });

  btn.addEventListener("mouseleave", () => {
    clearTimeout(pressTimer);
    socket.emit("stop_mount");
  });

  // (optional) touch support
  btn.addEventListener("touchstart", e => { e.preventDefault(); btn.dispatchEvent(new Event("mousedown")); }, {passive:false});
  btn.addEventListener("touchend",   e => { e.preventDefault(); btn.dispatchEvent(new Event("mouseup"));   }, {passive:false});
});


// Stop button
document.getElementById("stop-mount").addEventListener("click", () => {
  socket.emit("stop_mount");
});

// Track Sun
trackBtn.addEventListener("click", () => {
  socket.emit("track_sun");
});

// Park Mount
parkBtn.addEventListener("click", () => {
  socket.emit("park_mount");
});

// Unpark Mount
document.getElementById("unpark-mount").addEventListener("click", () => {
  socket.emit("unpark_mount");
});

// Mount status and coordinates
socket.on("mount_status", (status) => {
  mountStatus.textContent = status;
});

socket.on("mount_coordinates", (coords) => {
  if (raMount)  raMount.textContent  = data.ra_str  || "--:--:--";
  if (decMount) decMount.textContent = data.dec_str || "--:--:--";

  if (data.az != null && data.alt != null) {
    mountDot.az  = parseFloat(data.az);
    mountDot.alt = parseFloat(data.alt);
    drawSunPath();
  }

});


// === SECTION: FOCUSER CONTROL ===

function nstepMove(direction) {
  socket.emit("nstep_move", {
    direction: direction,
  });
}

// Receive focuser feedback from backend (INDIGO)
socket.on("nstep_position", (data) => {
  if ("set" in data) {
    document.getElementById("nstepSetPosition").textContent = data.set;
  }
  if ("current" in data) {
    document.getElementById("nstepCurrentPosition").textContent = data.current;
  }
});


// === SECTION: SCIENCE CAMERA ===

const img = document.getElementById("fc-preview");
const indicator = document.getElementById("fc-status-indicator");
let isPreviewRunning = false;
let previewPoll = null;

function startFcPreview() {
  if (isPreviewRunning) return;
  socket.emit("start_fc_preview");
  isPreviewRunning = true;

  img.classList.remove("opacity-50", "max-w-[300px]", "bg-gray-400");

  if (previewPoll) clearInterval(previewPoll);
  previewPoll = setInterval(() => {
    img.src = `http://${piIp}:8082/fc_preview.jpg?cache=${Date.now()}`;
  }, 500);

  // Move these outside the interval so they don’t reassign every time
  img.onload = () => {
    indicator.classList.replace("bg-red-500", "bg-green-500");
    img.classList.remove("opacity-50", "max-w-[300px]");
  };

  img.onerror = () => {
    indicator.classList.replace("bg-green-500", "bg-red-500");
    img.src = "/static/no_preview.png";
    img.classList.add("opacity-50", "max-w-[300px]");
  };
}

function stopFcPreview() {
  if (!isPreviewRunning) return;
  socket.emit("stop_fc_preview");
  isPreviewRunning = false;

  if (previewPoll) clearInterval(previewPoll);
  previewPoll = null;

  img.src = "/static/no_preview.png";
  img.onload = null;
  img.onerror = null;

  indicator.classList.remove("bg-green-500");
  indicator.classList.add("bg-red-500");

  img.classList.add("opacity-50", "max-w-[300px]", "bg-gray-400");
}

function triggerFcCapture() {
  socket.emit("trigger_fc_capture");

  img.classList.add("ring", "ring-blue-400");

  setTimeout(() => {
    img.classList.remove("ring", "ring-blue-400");
  }, 500);
}

socket.on("fc_preview_status", (status) => {
  if (status) {
    startFcPreview();
  } else {
    stopFcPreview();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  socket.emit("get_fc_status");
});

window.startFcPreview = startFcPreview;
window.stopFcPreview = stopFcPreview;
window.triggerFcCapture = triggerFcCapture;

// === SECTION: DOME CAMERA STATUS INDICATOR ===

const domeDot = document.getElementById("dome-status-indicator");

function updateDomeStatus() {
  fetch("/ping_dome_status")
    .then((res) => {
      if (res.ok) {
        domeDot.classList.remove("bg-red-500");
        domeDot.classList.add("bg-green-500");
      } else {
        domeDot.classList.remove("bg-green-500");
        domeDot.classList.add("bg-red-500");
      }
    })
    .catch(() => {
      domeDot.classList.remove("bg-green-500");
      domeDot.classList.add("bg-red-500");
    });
}

setInterval(updateDomeStatus, 5000);
updateDomeStatus();

// === SECTION: ARDUINO CONTROL ===

// === Dome control ===
function setDome(state) {
  socket.emit("set_dome", { state });
  console.log("[ARDUINO] Setting dome state to:", state);
}

// === Etalon sliders ===
["1", "2"].forEach((index) => {
  const slider = document.getElementById(`etalon${index}Slider`);
  const valueLabel = document.getElementById(`etalon${index}Value`);

  if (slider && valueLabel) {
    slider.addEventListener("input", () => {
      const val = parseInt(slider.value);
      valueLabel.textContent = `${val}°`;
      socket.emit("set_etalon", {
        index: parseInt(index),
        value: val
      });
    });
  }
});

// === Unified state updater ===
socket.on("arduino_state", (state) => {
  setArduinoStatus(state.connected);
  console.log("[ARDUINO] Arduino state:", state);

  // Dome
  const domeLabel = document.getElementById("domeStatus");
  if (domeLabel) domeLabel.textContent = "Status: " + state.dome;

  // Etalons
  for (let i = 1; i <= 2; i++) {
    const val = state[`etalon${i}`];
    const slider = document.getElementById(`etalon${i}Slider`);
    const label = document.getElementById(`etalon${i}Value`);
    if (slider && label) {
      slider.value = val;
      label.textContent = `${val}°`;
    }
  }
});

// === Arduino Status Check ===
function updateArduinoStatus() {
  window._arduinoResponded = true;
  socket.emit("get_arduino_state");

  setTimeout(() => {
    if (!window._arduinoResponded) {
      setArduinoStatus(false);
    }
  }, 2000);
}

function setArduinoStatus(connected) {
  const dot = document.getElementById("arduinoStatusDot");
  const text = document.getElementById("arduinoStatusText");
  if (!dot || !text) return;

  dot.classList.remove("bg-green-500", "bg-gray-400", "animate-pulse", "bg-red-500");

  if (connected) {
    dot.classList.add("bg-green-500");
    text.textContent = "Connected";
  } else {
    dot.classList.add("bg-red-500", "animate-pulse");
    text.textContent = "Disconnected";
  }
}


// === SECTION: FILE HANDLER  ===
const tableBody = document.getElementById("file-table-body");
const statusSpan = document.getElementById("file-status");

function renderFileList(files) {
  if (!tableBody || !statusSpan) return;

  tableBody.innerHTML = "";

  if (files.length === 0) {
    const emptyRow = document.createElement("tr");
    emptyRow.innerHTML = `
      <td class="px-4 py-2 text-center text-gray-500" colspan="3">No files found</td>
    `;
    tableBody.appendChild(emptyRow);
    statusSpan.textContent = "Idle";
    return;
  }

  let currentStatus = "Idle";

  files.forEach((file) => {
    const row = document.createElement("tr");

    let rowClass = "";
    if (file.status === "Copied") rowClass = "bg-green-100";
    else if (file.status === "Copying") rowClass = "bg-yellow-100";
    else if (file.status === "Failed") rowClass = "bg-red-100";

    row.className = rowClass;

    row.innerHTML = `
      <td class="px-4 py-2">${file.name}</td>
      <td class="px-4 py-2">${file.size}</td>
      <td class="px-4 py-2">${file.modified}</td>
    `;
    tableBody.appendChild(row);

    if (file.status === "Copying" || file.status === "Failed") {
      currentStatus = file.status;
    }
  });

  statusSpan.textContent = currentStatus;
}

socket.on("file_watch_status", (data) => {
  if (!data || !data.status || !statusSpan) return;

  if (data.status === "connected") {
    statusSpan.textContent = "Connected";
    statusSpan.style.color = "green";
  } else if (data.status === "disconnected") {
    statusSpan.textContent = "Disconnected";
    statusSpan.style.color = "red";
  }
});

// Initial fetch as fallback (in case no socket event yet)
fetch("/get_file_list")
  .then((res) => res.json())
  .then(renderFileList)
  .catch((err) => {
    console.error("Initial file list error:", err);
    statusSpan.textContent = "Error";
  });

// === WebSocket listener ===
socket.on("file_list_update", (files) => {
  renderFileList(files);
});

// === SECTION: AUTOGUIDER MODULE ===

// === Autoguider UI wiring ===
const agImg   = document.getElementById("guiding-preview");
const agFPS   = document.getElementById("guiding-fps");
const agLock  = document.getElementById("guiding-lock");
const agDX    = document.getElementById("guiding-dx");
const agDY    = document.getElementById("guiding-dy");
const agR     = document.getElementById("guiding-r");
const agStat  = document.getElementById("autoguider-status");

document.getElementById("autoguider-on").addEventListener("click", () => {
  socket.emit("autoguider_start");
});
document.getElementById("autoguider-off").addEventListener("click", () => {
  socket.emit("autoguider_stop");
});

// overlay image pushed from backend as data URL
socket.on("guiding_overlay", (dataUrl) => {
  if (agImg) agImg.src = dataUrl;  // data:image/jpeg;base64,...
});

// status/metrics
socket.on("guiding_status", (s) => {
  if (agStat) agStat.textContent = s?.status ?? "--";
  if (agFPS)  agFPS.textContent  = s?.fps ?? "--";
  if (agLock) agLock.textContent = s?.locked ? "YES" : "NO";
  if (agDX)   agDX.textContent   = s?.dx ?? "--";
  if (agDY)   agDY.textContent   = s?.dy ?? "--";
  if (agR)    agR.textContent    = s?.r  ?? "--";
});

// pull an initial status after connect
socket.on("connect", () => {
  socket.emit("autoguider_get_status");
});

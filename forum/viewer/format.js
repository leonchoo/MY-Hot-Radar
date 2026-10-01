// Shared timestamp formatter for all Forum Viewer pages.
// Single source of truth — DO NOT duplicate this logic in any other JS file.
//
// Contract:
//   input:  ISO 8601 UTC string with 'Z' suffix (e.g. "2026-10-01T07:15:40Z")
//   output: "YYYY-MM-DD HH:MM:SS MYT" rendered in Asia/Kuala_Lumpur (UTC+8, no DST)
//
// Why Intl.DateTimeFormat with timeZone:
//   - No dependence on the browser's local timezone (the bug that caused
//     "07:15:40" to be shown to 彪哥 in UTC environment)
//   - No manual day/month/year rollover math (the bug that produced
//     "2026-09-31" / "2026-12-32" / "2026-02-29" in 2026)
//   - Handles leap years, month boundaries, and DST correctly (Malaysia has
//     no DST so UTC+8 is always true, but the API still handles edge cases).
//
// Forbidden patterns (we will reject in code review):
//   - .replace("Z", "") without timezone conversion
//   - manual +8 arithmetic with day overflow
//   - new Date(iso).toLocaleString() without explicit timeZone
//   - any double-application of the formatter (input is always UTC Z)

(function (global) {
  "use strict";

  // Cached Intl parts formatters — same string every call, but we avoid
  // reconstructing the formatter for performance.
  const _fmtDateTime = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kuala_Lumpur",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const _fmtDateOnly = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kuala_Lumpur",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const _fmtTimeOnly = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kuala_Lumpur",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  function _isValidIsoUtc(s) {
    // Loose check: YYYY-MM-DDTHH:MM:SS(.fff)?Z
    return typeof s === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(s);
  }

  function _pad2(n) {
    return String(n).padStart(2, "0");
  }

  /**
   * Format any value (ISO string, Date, epoch ms) as a MYT string.
   * Returns "" for empty/null, and "—" for unparseable input (NEVER raw
   * garbage like "2026-09-31" or "2026-12-32").
   */
  function formatMyt(value) {
    if (value === null || value === undefined || value === "") return "";
    let d;
    if (value instanceof Date) {
      d = value;
    } else if (typeof value === "number") {
      d = new Date(value);
    } else if (typeof value === "string") {
      // The Python API always returns "Z"-suffixed UTC ISO. We require
      // exactly that — anything else (e.g. naive local time, or a
      // re-formatted MYT string from a previous formatter call) must
      // return "—" to prevent accidental double-conversion.
      if (!_isValidIsoUtc(value)) return "—";
      d = new Date(value);
    } else {
      return "—";
    }
    if (Number.isNaN(d.getTime())) return "—";

    const parts = _fmtDateTime.formatToParts(d);
    // parts: {type:"year",value:"2026"},{type:"month",value:"10"},...
    let y = "", mo = "", da = "", h = "", mi = "", s = "";
    for (const p of parts) {
      if (p.type === "year") y = p.value;
      else if (p.type === "month") mo = p.value;
      else if (p.type === "day") da = p.value;
      else if (p.type === "hour") h = p.value;
      else if (p.type === "minute") mi = p.value;
      else if (p.type === "second") s = p.value;
    }
    // Defensive: Intl can return "24" for hour in some environments when
    // hour12:false is combined with certain timezones. Force 2-digit.
    return `${y}-${_pad2(parseInt(mo, 10))}-${_pad2(parseInt(da, 10))} ` +
           `${_pad2(parseInt(h, 10))}:${_pad2(parseInt(mi, 10))}:${_pad2(parseInt(s, 10))} MYT`;
  }

  /** Format as date only "YYYY-MM-DD MYT". */
  function formatMytDate(value) {
    if (value === null || value === undefined || value === "") return "";
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    const parts = _fmtDateOnly.formatToParts(d);
    let y = "", mo = "", da = "";
    for (const p of parts) {
      if (p.type === "year") y = p.value;
      else if (p.type === "month") mo = p.value;
      else if (p.type === "day") da = p.value;
    }
    return `${y}-${_pad2(parseInt(mo, 10))}-${_pad2(parseInt(da, 10))} MYT`;
  }

  /** Format as time only "HH:MM:SS MYT". */
  function formatMytTime(value) {
    if (value === null || value === undefined || value === "") return "";
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    const parts = _fmtTimeOnly.formatToParts(d);
    let h = "", mi = "", s = "";
    for (const p of parts) {
      if (p.type === "hour") h = p.value;
      else if (p.type === "minute") mi = p.value;
      else if (p.type === "second") s = p.value;
    }
    return `${_pad2(parseInt(h, 10))}:${_pad2(parseInt(mi, 10))}:${_pad2(parseInt(s, 10))} MYT`;
  }

  // Export
  global.MYT_FORMAT = {
    formatMyt: formatMyt,
    formatMytDate: formatMytDate,
    formatMytTime: formatMytTime,
    /** Backward-compat alias used by Phase 7 human_tips.js. */
    utcToMyt: formatMyt,
  };
})(window);

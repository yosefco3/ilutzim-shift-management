/**
 * Trigger a browser download for a Blob (the anchor-click dance in one place).
 * Used by the export page and the Weeks-page saved-schedule download.
 */
export function triggerBlobDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/**
 * Build a meaningful export filename: "<what>_<week start date>.xlsx".
 *
 * The download name is what the admin sees on disk, so instead of the opaque
 * week UUID we key it on the week's start date (Sunday, ISO yyyy-mm-dd). That
 * says both *what* the file is and *which week* it belongs to, and it sorts
 * chronologically in a folder full of weekly exports.
 *
 * @param {string} what       content prefix, e.g. 'guard-positions' | 'schedule'
 * @param {string} startDate  the week's start_date (ISO date or datetime string)
 * @param {string} [ext]      file extension without the dot (default 'xlsx')
 */
export function weeklyExportFilename(what, startDate, ext = 'xlsx') {
  const week = (startDate || '').slice(0, 10); // tolerate a datetime, keep yyyy-mm-dd
  return week ? `${what}_${week}.${ext}` : `${what}.${ext}`;
}

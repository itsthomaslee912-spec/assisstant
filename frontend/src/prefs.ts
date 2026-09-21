export type ViewMode = "list" | "table" | "card";
export type FontFamily = "dm-sans" | "inter" | "source-serif" | "ibm-plex" | "system";
export type FontSize = "small" | "medium" | "large";

const VIEW_KEY = "email-checker-view";
const FONT_KEY = "email-checker-font";
const FONT_SIZE_KEY = "email-checker-font-size";

export const VIEW_MODES: ViewMode[] = ["list", "table", "card"];
export const FONT_FAMILIES: { id: FontFamily; label: string }[] = [
  { id: "dm-sans", label: "DM Sans" },
  { id: "inter", label: "Inter" },
  { id: "source-serif", label: "Source Serif" },
  { id: "ibm-plex", label: "IBM Plex Sans" },
  { id: "system", label: "System UI" },
];
export const FONT_SIZES: { id: FontSize; label: string }[] = [
  { id: "small", label: "Small" },
  { id: "medium", label: "Medium" },
  { id: "large", label: "Large" },
];

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

export function loadViewMode(): ViewMode {
  const value = readStorage(VIEW_KEY);
  if (value === "list" || value === "table" || value === "card") return value;
  return "list";
}

export function saveViewMode(mode: ViewMode): void {
  writeStorage(VIEW_KEY, mode);
}

export function loadFontFamily(): FontFamily {
  const value = readStorage(FONT_KEY);
  if (
    value === "dm-sans" ||
    value === "inter" ||
    value === "source-serif" ||
    value === "ibm-plex" ||
    value === "system"
  ) {
    return value;
  }
  return "dm-sans";
}

export function applyFontFamily(font: FontFamily): void {
  document.documentElement.dataset.font = font;
}

export function saveFontFamily(font: FontFamily): void {
  writeStorage(FONT_KEY, font);
  applyFontFamily(font);
}

export function loadFontSize(): FontSize {
  const value = readStorage(FONT_SIZE_KEY);
  if (value === "small" || value === "medium" || value === "large") return value;
  return "medium";
}

export function applyFontSize(size: FontSize): void {
  document.documentElement.dataset.fontSize = size;
}

export function saveFontSize(size: FontSize): void {
  writeStorage(FONT_SIZE_KEY, size);
  applyFontSize(size);
}

export function applyAppearancePrefs(): void {
  applyFontFamily(loadFontFamily());
  applyFontSize(loadFontSize());
}

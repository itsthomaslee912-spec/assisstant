import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ConfigProvider, theme as antdTheme } from "antd";

export type ThemeMode = "dark" | "light" | "system";
export type Density = "comfortable" | "compact";
export type FontSize = "small" | "medium" | "large";
export type FontFamily = "inter" | "system" | "serif";

export interface AppearanceSettings {
  theme: ThemeMode;
  density: Density;
  fontSize: FontSize;
  fontFamily: FontFamily;
}

const STORAGE_KEY = "bidflow-appearance";
const defaults: AppearanceSettings = { theme: "dark", density: "comfortable", fontSize: "medium", fontFamily: "inter" };
const fontFamilies: Record<FontFamily, string> = {
  inter: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  system: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  serif: "Georgia, 'Times New Roman', serif",
};
const fontSizes: Record<FontSize, number> = { small: 13, medium: 14, large: 16 };

interface AppearanceContextValue {
  settings: AppearanceSettings;
  resolvedTheme: "dark" | "light";
  updateSettings: (next: Partial<AppearanceSettings>) => void;
  resetSettings: () => void;
}

const AppearanceContext = createContext<AppearanceContextValue | null>(null);

function savedSettings(): AppearanceSettings {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") }; }
  catch { return defaults; }
}

export function AppearanceProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<AppearanceSettings>(savedSettings);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);
  const resolvedTheme = settings.theme === "system" ? (systemDark ? "dark" : "light") : settings.theme;

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.density = settings.density;
    document.documentElement.style.fontFamily = fontFamilies[settings.fontFamily];
    document.documentElement.style.fontSize = `${fontSizes[settings.fontSize]}px`;
  }, [settings, resolvedTheme]);

  const value = useMemo<AppearanceContextValue>(() => ({
    settings,
    resolvedTheme,
    updateSettings: next => setSettings(current => ({ ...current, ...next })),
    resetSettings: () => setSettings(defaults),
  }), [settings, resolvedTheme]);

  const dark = resolvedTheme === "dark";
  return <AppearanceContext.Provider value={value}>
    <ConfigProvider theme={{
      algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: "#6d7cff", colorInfo: "#6d7cff", colorSuccess: "#2dbb91",
        colorWarning: "#eaa63a", colorError: "#ee5d6c",
        colorBgBase: dark ? "#07111f" : "#f4f7fb",
        colorBgContainer: dark ? "#0d1a2c" : "#ffffff",
        colorBorder: dark ? "#20334d" : "#dce4ef",
        borderRadius: 12, borderRadiusLG: 18,
        controlHeight: settings.density === "compact" ? 34 : 40,
        fontSize: fontSizes[settings.fontSize], fontFamily: fontFamilies[settings.fontFamily],
      },
      components: {
        Button: { fontWeight: 650, primaryShadow: "0 8px 24px rgba(92, 111, 255, .26)" },
        Card: { bodyPadding: settings.density === "compact" ? 18 : 24, headerBg: "transparent" },
        Table: { headerBg: dark ? "#101f34" : "#f5f7fb", headerColor: dark ? "#aebbd0" : "#53627a", rowHoverBg: dark ? "#12233a" : "#f7f9fc", borderColor: dark ? "#1c304b" : "#e2e8f1" },
        Input: { activeShadow: "0 0 0 3px rgba(109, 124, 255, .14)" },
        Select: { activeOutlineColor: "rgba(109, 124, 255, .14)" },
      },
    }}>{children}</ConfigProvider>
  </AppearanceContext.Provider>;
}

export function useAppearance() {
  const context = useContext(AppearanceContext);
  if (!context) throw new Error("useAppearance must be used inside AppearanceProvider");
  return context;
}

import { Card, Radio, Typography } from "antd";
import { BgColorsOutlined, CompressOutlined, FontSizeOutlined, FormatPainterOutlined } from "@ant-design/icons";
import { useAppearance } from "../appearance";

const choices = {
  theme: [
    { value: "dark", label: "Dark", hint: "Low-light workspace", swatch: "theme-dark" },
    { value: "light", label: "Light", hint: "Bright and clear", swatch: "theme-light" },
    { value: "system", label: "System", hint: "Match your device", swatch: "theme-system" },
  ],
  density: [
    { value: "comfortable", label: "Comfortable", hint: "More breathing room" },
    { value: "compact", label: "Compact", hint: "More content on screen" },
  ],
  fontSize: [
    { value: "small", label: "Small", hint: "13 px" },
    { value: "medium", label: "Default", hint: "14 px" },
    { value: "large", label: "Large", hint: "16 px" },
  ],
  fontFamily: [
    { value: "inter", label: "Inter", hint: "Clean and modern" },
    { value: "system", label: "System", hint: "Native to your device" },
    { value: "serif", label: "Serif", hint: "Traditional and readable" },
  ],
} as const;

export default function SettingsPage() {
  const { settings, resolvedTheme, updateSettings } = useAppearance();
  return <div className="page-stack settings-page">
    <div className="settings-grid">
      <SettingCard icon={<BgColorsOutlined />} title="Theme" description={`Currently using ${resolvedTheme} mode`}>
        <Radio.Group className="choice-grid theme-choices" value={settings.theme} onChange={event => updateSettings({ theme: event.target.value })}>
          {choices.theme.map(item => <Radio.Button key={item.value} value={item.value}><span className={`theme-swatch ${item.swatch}`}><i /><i /></span><strong>{item.label}</strong><small>{item.hint}</small></Radio.Button>)}
        </Radio.Group>
      </SettingCard>
      <SettingCard icon={<CompressOutlined />} title="Appearance" description="Choose the spacing density of controls and cards">
        <Radio.Group className="choice-grid two-column" value={settings.density} onChange={event => updateSettings({ density: event.target.value })}>
          {choices.density.map(item => <Radio.Button key={item.value} value={item.value}><strong>{item.label}</strong><small>{item.hint}</small></Radio.Button>)}
        </Radio.Group>
      </SettingCard>
      <SettingCard icon={<FontSizeOutlined />} title="Font size" description="Adjust text size across the application">
        <Radio.Group className="choice-grid" value={settings.fontSize} onChange={event => updateSettings({ fontSize: event.target.value })}>
          {choices.fontSize.map(item => <Radio.Button key={item.value} value={item.value}><strong>{item.label}</strong><small>{item.hint}</small></Radio.Button>)}
        </Radio.Group>
      </SettingCard>
      <SettingCard icon={<FormatPainterOutlined />} title="Font family" description="Select the typeface used throughout BidFlow">
        <Radio.Group className="choice-grid" value={settings.fontFamily} onChange={event => updateSettings({ fontFamily: event.target.value })}>
          {choices.fontFamily.map(item => <Radio.Button className={`font-${item.value}`} key={item.value} value={item.value}><strong>{item.label}</strong><small>{item.hint}</small></Radio.Button>)}
        </Radio.Group>
      </SettingCard>
    </div>
  </div>;
}

function SettingCard({ icon, title, description, children }: { icon: React.ReactNode; title: string; description: string; children: React.ReactNode }) {
  return <Card className="setting-card" bordered={false}><div className="setting-card-heading"><span>{icon}</span><div><Typography.Title level={5}>{title}</Typography.Title><Typography.Text type="secondary">{description}</Typography.Text></div></div>{children}</Card>;
}

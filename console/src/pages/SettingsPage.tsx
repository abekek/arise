import { useEffect, useState } from "react";
import { fetchSettings, updateSettings } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eye, EyeOff, CheckCircle } from "lucide-react";

interface Settings {
  openai_api_key?: string;
  anthropic_api_key?: string;
  aws_profile?: string;
  aws_region?: string;
  default_model?: string;
  sandbox_backend?: string;
  failure_threshold?: number;
}

const MODELS = [
  "claude-opus-4-5",
  "claude-sonnet-4-5",
  "gpt-4o",
  "gpt-4-turbo",
  "gemini-1.5-pro",
];

const SANDBOX_BACKENDS = ["docker", "e2b", "modal", "local"];

function PasswordInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        type={show ? "text" : "password"}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 pr-10 font-mono text-sm"
      />
      <button
        type="button"
        onClick={() => setShow(s => !s)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400 transition-colors"
      >
        {show ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="px-5 py-4 border-b border-zinc-800">
        <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
        {description && (
          <p className="text-xs text-zinc-500 mt-0.5">{description}</p>
        )}
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-zinc-400">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-zinc-600">{hint}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchSettings();
        setSettings(data ?? {});
      } catch {
        setSettings({});
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings(s => ({ ...s, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await updateSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      setError("Failed to save settings — is the backend running?");
    } finally {
      setSaving(false);
    }
  }

  const selectClass =
    "w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-sm rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-zinc-500";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Loading settings...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Settings</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Configure your ARISE environment</p>
        </div>
        <div className="flex items-center gap-3">
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-400">
              <CheckCircle size={14} /> Saved
            </span>
          )}
          <Button
            onClick={handleSave}
            disabled={saving}
            className="bg-emerald-600 hover:bg-emerald-500 text-white"
            size="sm"
          >
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl flex flex-col gap-5">
          {/* API Keys */}
          <Section
            title="API Keys"
            description="Keys are stored locally and never sent anywhere except the configured backends."
          >
            <div className="flex flex-col gap-4">
              <Field
                label="OpenAI API Key"
                hint="Used for GPT-4o and other OpenAI models"
              >
                <PasswordInput
                  value={settings.openai_api_key ?? ""}
                  onChange={v => set("openai_api_key", v)}
                  placeholder="sk-..."
                />
              </Field>
              <Field
                label="Anthropic API Key"
                hint="Used for Claude models"
              >
                <PasswordInput
                  value={settings.anthropic_api_key ?? ""}
                  onChange={v => set("anthropic_api_key", v)}
                  placeholder="sk-ant-..."
                />
              </Field>
            </div>
          </Section>

          {/* AWS */}
          <Section
            title="AWS"
            description="AWS credentials for sandbox and storage backends."
          >
            <div className="flex flex-col gap-4">
              <Field label="AWS Profile" hint="Credential profile from ~/.aws/credentials">
                <Input
                  value={settings.aws_profile ?? ""}
                  onChange={e => set("aws_profile", e.target.value)}
                  placeholder="default"
                  className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 font-mono text-sm"
                />
              </Field>
              <Field label="AWS Region">
                <Input
                  value={settings.aws_region ?? ""}
                  onChange={e => set("aws_region", e.target.value)}
                  placeholder="us-east-1"
                  className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 font-mono text-sm"
                />
              </Field>
            </div>
          </Section>

          {/* Defaults */}
          <Section title="Defaults" description="Default values used when creating new agents.">
            <div className="flex flex-col gap-4">
              <Field label="Default Model">
                <select
                  value={settings.default_model ?? MODELS[0]}
                  onChange={e => set("default_model", e.target.value)}
                  className={selectClass}
                >
                  {MODELS.map(m => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Default Sandbox Backend">
                <select
                  value={settings.sandbox_backend ?? SANDBOX_BACKENDS[0]}
                  onChange={e => set("sandbox_backend", e.target.value)}
                  className={selectClass}
                >
                  {SANDBOX_BACKENDS.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label="Failure Threshold"
                hint="Number of consecutive failures before triggering evolution (0–1 as fraction or integer count)"
              >
                <Input
                  type="number"
                  min={0}
                  step={0.05}
                  value={settings.failure_threshold ?? ""}
                  onChange={e =>
                    set("failure_threshold", parseFloat(e.target.value) || undefined)
                  }
                  placeholder="0.3"
                  className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 font-mono text-sm"
                />
              </Field>
            </div>
          </Section>

          {error && (
            <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
type Config = {
  version: number;
  enabled: boolean;
  approved: boolean;
  approval_reference: string;
  external_authorized: boolean;
  endpoint: string;
  model: string;
  key_env: string;
  allowed_purposes: string[];
  credential_configured: boolean;
};
type Props = {
  csrf: string;
  fetcher: (
    url: string,
    method?: string,
    body?: unknown,
    csrf?: string,
  ) => Promise<unknown>;
};
export function ModelPanel({ csrf, fetcher }: Props) {
  const [config, setConfig] = useState<Config | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    fetcher("/api/model/config")
      .then((v) => setConfig(v as Config))
      .catch((e) => setError((e as Error).message));
  }, [fetcher]);
  async function save() {
    if (!config) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fetcher(
        "/api/model/config",
        "PUT",
        { ...config, expected_version: config.version },
        csrf,
      );
      setConfig((await fetcher("/api/model/config")) as Config);
      setNotice("配置已保存，尚需连接和真实业务验证");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = (await fetcher(
        "/api/model/check",
        "POST",
        undefined,
        csrf,
      )) as { message: string };
      setNotice(result.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>获准模型连接</h2>
      <p>
        默认不启用。只允许配置经过批准的服务；外部追踪始终关闭。连接检验只发送固定合成探测文本，不含业务数据。
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {config && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <div className="account-form">
            <label>
              模型地址
              <input
                value={config.endpoint}
                placeholder="http://127.0.0.1:11434/v1"
                onChange={(e) =>
                  setConfig({ ...config, endpoint: e.target.value })
                }
              />
            </label>
            <label>
              模型名称
              <input
                value={config.model}
                onChange={(e) =>
                  setConfig({ ...config, model: e.target.value })
                }
              />
            </label>
            <label>
              密钥环境变量名称
              <input
                value={config.key_env}
                onChange={(e) =>
                  setConfig({ ...config, key_env: e.target.value })
                }
              />
            </label>
            <label>
              审批依据
              <input
                value={config.approval_reference}
                onChange={(e) =>
                  setConfig({ ...config, approval_reference: e.target.value })
                }
              />
            </label>
          </div>
          <p>
            凭证状态：
            {config.credential_configured
              ? "环境变量已配置（不回显）"
              : "尚未配置"}
            ；配置版本 {config.version}
          </p>
          {(["approved", "external_authorized", "enabled"] as const).map(
            (k, i) => (
              <label className="check" key={k}>
                <input
                  type="checkbox"
                  checked={config[k]}
                  onChange={(e) =>
                    setConfig({ ...config, [k]: e.target.checked })
                  }
                />
                {["服务已批准", "已获非本机网络授权", "启用模型"][i]}
              </label>
            ),
          )}
          <fieldset>
            <legend>允许的数据用途</legend>
            {["agent", "papers"].map((p) => (
              <label className="check" key={p}>
                <input
                  type="checkbox"
                  checked={config.allowed_purposes.includes(p)}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      allowed_purposes: e.target.checked
                        ? [...config.allowed_purposes, p]
                        : config.allowed_purposes.filter((v) => v !== p),
                    })
                  }
                />
                {p === "agent" ? "Agent查询解释" : "论文语义解析"}
              </label>
            ))}
          </fieldset>
          <button disabled={busy}>保存模型配置</button>{" "}
          <button
            className="secondary"
            type="button"
            disabled={busy}
            onClick={() => void check()}
          >
            检验已保存连接
          </button>
        </form>
      )}
    </section>
  );
}

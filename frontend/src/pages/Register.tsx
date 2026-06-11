import { Button, Form, Input, message, Radio } from "antd";
import { useState } from "react";
import { register, type AuthUser } from "../api/client";

const TEXT = {
  title: "\u521b\u5efa\u8d26\u53f7",
  subtitle: "\u6ce8\u518c\u540e\u81ea\u52a8\u8fdb\u5165\u804a\u5929\u754c\u9762",
  emailRegister: "\u90ae\u7bb1\u6ce8\u518c",
  phoneRegister: "\u624b\u673a\u53f7\u6ce8\u518c",
  email: "\u90ae\u7bb1",
  phone: "\u624b\u673a\u53f7",
  password: "\u5bc6\u7801",
  required: "\u5fc5\u586b",
  invalidEmail: "\u90ae\u7bb1\u683c\u5f0f\u4e0d\u6b63\u786e",
  invalidPhone: "\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u624b\u673a\u53f7\u683c\u5f0f",
  phonePlaceholder: "\u8bf7\u8f93\u5165\u624b\u673a\u53f7",
  minPassword: "\u81f3\u5c11 6 \u4f4d",
  minPasswordRule: "\u5bc6\u7801\u81f3\u5c11 6 \u4f4d",
  register: "\u6ce8\u518c",
  registerSuccess: "\u6ce8\u518c\u6210\u529f",
  registerFailed: "\u6ce8\u518c\u5931\u8d25",
  hasAccount: "\u5df2\u6709\u8d26\u53f7\uff1f",
  goLogin: "\u53bb\u767b\u5f55"
};

type RegisterProps = {
  onSuccess: (token: string, user: AuthUser) => void;
  onGoLogin: () => void;
};

export function Register({ onSuccess, onGoLogin }: RegisterProps) {
  const [mode, setMode] = useState<"email" | "phone">("email");

  const submit = async (values: { email?: string; phone?: string; password: string }) => {
    try {
      const result = await register({
        email: mode === "email" ? values.email : undefined,
        phone: mode === "phone" ? values.phone : undefined,
        password: values.password
      });
      message.success(TEXT.registerSuccess);
      onSuccess(result.access_token, result.user);
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.registerFailed);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-panel">
        <div className="auth-title">{TEXT.title}</div>
        <div className="auth-subtitle">{TEXT.subtitle}</div>
        <Form layout="vertical" onFinish={submit}>
          <Radio.Group className="auth-mode" value={mode} onChange={(event) => setMode(event.target.value)}>
            <Radio.Button value="email">{TEXT.emailRegister}</Radio.Button>
            <Radio.Button value="phone">{TEXT.phoneRegister}</Radio.Button>
          </Radio.Group>

          {mode === "email" ? (
            <Form.Item
              label={TEXT.email}
              name="email"
              rules={[
                { required: true, message: TEXT.required },
                { type: "email", message: TEXT.invalidEmail }
              ]}
            >
              <Input size="large" placeholder="test@example.com" />
            </Form.Item>
          ) : (
            <Form.Item
              label={TEXT.phone}
              name="phone"
              rules={[
                { required: true, message: TEXT.required },
                { pattern: /^1[3-9]\d{9}$/, message: TEXT.invalidPhone }
              ]}
            >
              <Input size="large" placeholder={TEXT.phonePlaceholder} />
            </Form.Item>
          )}

          <Form.Item
            label={TEXT.password}
            name="password"
            rules={[
              { required: true, message: TEXT.required },
              { min: 6, message: TEXT.minPasswordRule }
            ]}
          >
            <Input.Password size="large" placeholder={TEXT.minPassword} />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>
            {TEXT.register}
          </Button>
        </Form>
        <div className="auth-switch">
          {TEXT.hasAccount}
          <Button type="link" onClick={onGoLogin}>
            {TEXT.goLogin}
          </Button>
        </div>
      </div>
    </div>
  );
}

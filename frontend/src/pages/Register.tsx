import { Button, Form, Input, message, Radio } from "antd";
import { useState } from "react";
import { register, type AuthUser } from "../api/client";

const TEXT = {
  title: "创建账号",
  subtitle: "注册后自动进入聊天界面",
  emailRegister: "邮箱注册",
  phoneRegister: "手机号注册",
  email: "邮箱",
  phone: "手机号",
  password: "密码",
  required: "必填",
  invalidEmail: "邮箱格式不正确",
  invalidPhone: "请输入正确的手机号格式",
  phonePlaceholder: "请输入手机号",
  minPassword: "至少 6 位",
  minPasswordRule: "密码至少 6 位",
  register: "注册",
  registerSuccess: "注册成功",
  registerFailed: "注册失败",
  hasAccount: "已有账号？",
  goLogin: "去登录"
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

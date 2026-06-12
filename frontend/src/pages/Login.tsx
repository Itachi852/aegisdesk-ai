import { Alert, Button, Form, Input, message } from "antd";
import { useState } from "react";
import { login, type AuthUser } from "../api/client";

const TEXT = {
  subtitle: "登录企业智能客服系统",
  account: "邮箱或手机号",
  password: "密码",
  required: "必填",
  invalidAccount: "请输入正确的邮箱或手机号格式",
  minPassword: "至少 6 位",
  minPasswordRule: "密码至少 6 位",
  login: "登录",
  loginSuccess: "登录成功",
  loginFailed: "登录失败",
  invalidCredentials: "账号或密码错误，请重新输入",
  serviceError: "登录失败，请检查后端服务是否正常",
  noAccount: "还没有账号？",
  goRegister: "去注册"
};

const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const PHONE_PATTERN = /^1[3-9]\d{9}$/;

type LoginProps = {
  onSuccess: (token: string, user: AuthUser) => void;
  onGoRegister: () => void;
};

export function Login({ onSuccess, onGoRegister }: LoginProps) {
  const [submitting, setSubmitting] = useState(false);
  const [errorText, setErrorText] = useState("");

  const submit = async (values: { account: string; password: string }) => {
    setSubmitting(true);
    setErrorText("");
    try {
      const result = await login(values.account, values.password);
      message.success(TEXT.loginSuccess);
      onSuccess(result.access_token, result.user);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "";
      if (errorMessage.includes("Failed to fetch") || errorMessage.includes("NetworkError")) {
        message.error(TEXT.serviceError);
        setErrorText(TEXT.serviceError);
      } else if (errorMessage.includes("Invalid account or password")) {
        message.error(TEXT.invalidCredentials);
        setErrorText(TEXT.invalidCredentials);
      } else {
        const nextError = errorMessage || TEXT.loginFailed;
        message.error(nextError);
        setErrorText(nextError);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-panel">
        <div className="auth-title">AegisDesk AI</div>
        <div className="auth-subtitle">{TEXT.subtitle}</div>
        <Form layout="vertical" onFinish={submit}>
          <Form.Item
            label={TEXT.account}
            name="account"
            rules={[
              { required: true, message: TEXT.required },
              {
                validator: (_, value?: string) => {
                  const account = value?.trim() || "";
                  if (!account) return Promise.resolve();
                  const isEmail = account.includes("@");
                  const valid = isEmail ? EMAIL_PATTERN.test(account) : PHONE_PATTERN.test(account);
                  return valid ? Promise.resolve() : Promise.reject(new Error(TEXT.invalidAccount));
                }
              }
            ]}
          >
            <Input size="large" placeholder="test@example.com" />
          </Form.Item>
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
          {errorText ? <Alert className="auth-error" type="error" message={errorText} showIcon /> : null}
          <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
            {TEXT.login}
          </Button>
        </Form>
        <div className="auth-switch">
          {TEXT.noAccount}
          <Button type="link" onClick={onGoRegister}>
            {TEXT.goRegister}
          </Button>
        </div>
      </div>
    </div>
  );
}

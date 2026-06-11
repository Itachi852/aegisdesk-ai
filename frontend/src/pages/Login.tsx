import { Alert, Button, Form, Input, message } from "antd";
import { useState } from "react";
import { login, type AuthUser } from "../api/client";

const TEXT = {
  subtitle: "\u767b\u5f55\u4f01\u4e1a\u667a\u80fd\u5ba2\u670d\u7cfb\u7edf",
  account: "\u90ae\u7bb1\u6216\u624b\u673a\u53f7",
  password: "\u5bc6\u7801",
  required: "\u5fc5\u586b",
  invalidAccount: "\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u90ae\u7bb1\u6216\u624b\u673a\u53f7\u683c\u5f0f",
  minPassword: "\u81f3\u5c11 6 \u4f4d",
  minPasswordRule: "\u5bc6\u7801\u81f3\u5c11 6 \u4f4d",
  login: "\u767b\u5f55",
  loginSuccess: "\u767b\u5f55\u6210\u529f",
  loginFailed: "\u767b\u5f55\u5931\u8d25",
  invalidCredentials: "\u8d26\u53f7\u6216\u5bc6\u7801\u9519\u8bef\uff0c\u8bf7\u91cd\u65b0\u8f93\u5165",
  serviceError: "\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1\u662f\u5426\u6b63\u5e38",
  noAccount: "\u8fd8\u6ca1\u6709\u8d26\u53f7\uff1f",
  goRegister: "\u53bb\u6ce8\u518c"
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

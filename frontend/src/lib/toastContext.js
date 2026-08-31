import { createContext, useContext } from "react";

const noop = () => {};

export const ToastContext = createContext({
  push: noop,
  dismiss: noop,
  success: noop,
  error: noop,
  info: noop,
});

export function useToast() {
  return useContext(ToastContext);
}

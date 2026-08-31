import { createContext, useContext } from "react";

/* Context + hook only — no components in this module, so it stays clean under
 * `react/only-export-components`. The provider lives in
 * components/ui/ToastProvider.jsx.
 */

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

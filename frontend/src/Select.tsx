import { createElement, type ComponentProps } from "react";

// Keep native form/keyboard behavior while giving long selected labels a bounded text container.
export function Select({ children, ...props }: ComponentProps<"select">) {
  return (
    <select {...props}>
      <button
        type="button"
        className="select-value"
        tabIndex={-1}
        aria-hidden="true"
      >
        {createElement("selectedcontent")}
      </button>
      {children}
    </select>
  );
}

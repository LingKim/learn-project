import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface InputFieldProps extends React.ComponentProps<typeof Input> {
  error?: string;
  label: string;
}

function InputField({ error, id, label, className, ...props }: InputFieldProps) {
  const errorId = error && id ? `${id}-error` : undefined;

  return (
    <div>
      <Label className="text-foreground" htmlFor={id}>
        {label}
      </Label>
      <Input
        {...props}
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={errorId}
        className={cn("mt-2 h-12 bg-surface px-3.5", className)}
      />
      {error ? (
        <p id={errorId} className="mt-1.5 text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export { InputField };

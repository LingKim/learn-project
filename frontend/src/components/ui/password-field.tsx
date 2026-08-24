"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface PasswordFieldProps extends Omit<React.ComponentProps<typeof Input>, "type"> {
  error?: string;
  label: string;
}

function PasswordField({ error, id, label, className, ...props }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const errorId = error && id ? `${id}-error` : undefined;

  return (
    <div>
      <Label className="text-foreground" htmlFor={id}>
        {label}
      </Label>
      <div className="relative mt-2">
        <Input
          {...props}
          id={id}
          type={visible ? "text" : "password"}
          aria-invalid={Boolean(error)}
          aria-describedby={errorId}
          className={cn("h-12 bg-surface px-3.5 pr-12", className)}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute inset-y-0 right-0 h-12 min-h-12 rounded-l-none text-muted-foreground hover:text-foreground focus-visible:outline-offset-[-3px]"
          aria-label={visible ? `隐藏${label}` : `显示${label}`}
          onClick={() => setVisible((value) => !value)}
        >
          {visible ? (
            <EyeOff aria-hidden="true" className="size-[1.125rem]" />
          ) : (
            <Eye aria-hidden="true" className="size-[1.125rem]" />
          )}
        </Button>
      </div>
      {error ? (
        <p id={errorId} className="mt-1.5 text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export { PasswordField };

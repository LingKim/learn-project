"use client";

import * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

interface CheckboxFieldProps extends React.ComponentProps<typeof Checkbox> {
  label: string;
}

function CheckboxField({ id, label, ...props }: CheckboxFieldProps) {
  const generatedId = React.useId();
  const checkboxId = id ?? generatedId;

  return (
    <Label className="min-h-11 w-fit cursor-pointer text-muted-foreground" htmlFor={checkboxId}>
      <Checkbox {...props} id={checkboxId} />
      {label}
    </Label>
  );
}

export { CheckboxField };

"use client";

import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type TagFieldProps = {
  id: string;
  label: string;
  description: string;
  placeholder: string;
  value: string[];
  maxLength: number;
  disabled?: boolean;
  onChange: (value: string[]) => void;
};

export function TagField({
  id,
  label,
  description,
  placeholder,
  value,
  maxLength,
  disabled,
  onChange,
}: TagFieldProps) {
  const [draft, setDraft] = useState("");

  function addTag() {
    const next = draft.trim();
    if (!next || next.length > maxLength) return;
    if (!value.some((item) => item.toLocaleLowerCase() === next.toLocaleLowerCase())) {
      onChange([...value, next]);
    }
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <p className="text-xs leading-5 text-muted-foreground">{description}</p>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label={`${label}已添加项`}>
          {value.map((tag) => (
            <span
              key={tag}
              className="inline-flex min-h-8 items-center gap-1 rounded-full border border-border bg-primary/20 px-3 text-xs font-medium"
            >
              {tag}
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-primary/30 focus-visible:outline-2 focus-visible:outline-ring"
                aria-label={`移除${tag}`}
                disabled={disabled}
                onClick={() => onChange(value.filter((item) => item !== tag))}
              >
                <X aria-hidden="true" className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          maxLength={maxLength}
          disabled={disabled || value.length >= 30}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === ",") {
              event.preventDefault();
              addTag();
            }
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled || !draft.trim() || draft.trim().length > maxLength}
          onClick={addTag}
        >
          <Plus aria-hidden="true" />
          添加
        </Button>
      </div>
    </div>
  );
}

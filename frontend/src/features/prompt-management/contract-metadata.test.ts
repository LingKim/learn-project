import { expect, it } from "vitest";
import type { DefinitionView } from "./api";
import { registeredContractRecord, registeredContractText } from "./contract-metadata";

it("注册契约只接受实际对象并逐字段收窄，旧定义/未知结构不伪造契约", () => {
  const definition = {
    registered_contract: {
      definition_key: "question_generator/practice_generate",
      tools: [],
      model: 123,
    },
  } as unknown as DefinitionView;
  expect(registeredContractText(definition, "definition_key")).toBe(
    "question_generator/practice_generate",
  );
  expect(registeredContractText(definition, "tools")).toBeNull();
  expect(registeredContractText(definition, "model")).toBeNull();
  expect(registeredContractText(definition, "unknown")).toBeNull();
  for (const registered_contract of [null, undefined, [], "invalid"]) {
    expect(
      registeredContractRecord({ registered_contract } as unknown as DefinitionView),
    ).toBeNull();
  }
});

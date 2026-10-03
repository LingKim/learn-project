import { useEffect, useRef } from "react";

/** 捕获请求所属的页面生命周期；离开再返回同一地址也不能接纳旧请求的续行。 */
export function useActiveContext(context: string) {
  const mounted = useRef(true);
  const current = useRef({ context });
  if (current.current.context !== context) current.current = { context };
  const captured = current.current;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return () => mounted.current && current.current === captured;
}

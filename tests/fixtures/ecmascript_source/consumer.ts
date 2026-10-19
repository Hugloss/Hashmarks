import primary, { gateway as client, type Channel } from "./gateway";
import * as registry from "./gateway";
import type { Channel as SourceChannel } from "./gateway";
export { gateway as publicClient } from "./gateway";

const transport = client;
const { send: transmit, receive, nested: { close }, [method]: chosen, ...rest } = transport;
transport.send(payload);
transmit(payload);
transport["send"]?.(payload);
transport[method](payload);
const key = "se" + "nd";
transport[key](payload);
let mutable = transport;
mutable = registry.gateway;

function relay(transport: Channel) {
  transport.send(payload);
}
type Send = typeof transport.send;
const display = "transport.stringOnly()";
const template = `transport.templateOnly()`;
/* transport.commentOnly() */
new registry.Builder();

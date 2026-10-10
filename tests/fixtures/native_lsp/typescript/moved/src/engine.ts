// Move the declaration without changing its identity.

import { Contract } from "./contract";

export class Engine implements Contract {
    normalize(value: string): string {
        return value.trim();
    }
}

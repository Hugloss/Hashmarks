import { Contract } from "./contract";

export class Engine implements Contract {
    normalize(value: string): string {
        return value.trim();
    }
}

export class Other implements Contract {
    normalize(value: string): string {
        return value.toLowerCase();
    }
}

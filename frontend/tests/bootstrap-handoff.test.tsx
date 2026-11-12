import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {it,expect,vi} from "vitest";
import {BootstrapHandoff} from "../src/BootstrapHandoff";

const publicKey="-----BEGIN PUBLIC KEY-----\npublic demonstration\n-----END PUBLIC KEY-----\n";

// Exact PEM line breaks and a selectable username remain available independently of clipboard support.
it("shows and copies only actionable public values",async()=>{
 const user=userEvent.setup();const generate=vi.fn();
 const c=render(<BootstrapHandoff username="otm-bootstrap-example" publicKey={publicKey} canGenerate={false} busy={false} generate={generate}/>);
 expect(screen.getByLabelText("Bootstrap username")).toHaveValue("otm-bootstrap-example");
 expect(screen.getByLabelText("Public API key (PEM)")).toHaveValue(publicKey);
 expect(screen.getByLabelText("Public API key (PEM)")).toHaveAttribute("readonly");
 expect(screen.getByLabelText("Public API key (PEM)")).not.toBeDisabled();
 await user.click(screen.getByRole("button",{name:"Copy username"}));expect(await navigator.clipboard.readText()).toBe("otm-bootstrap-example");
 expect(screen.getByRole("status")).toHaveTextContent("Copied username");
 await user.click(screen.getByRole("button",{name:"Copy public key"}));expect(await navigator.clipboard.readText()).toBe(publicKey);
 expect(screen.getByRole("status")).toHaveTextContent("Copied public key");
 vi.spyOn(navigator.clipboard,"writeText").mockRejectedValueOnce(new Error("unavailable"));
 await user.click(screen.getByRole("button",{name:"Copy username"}));expect(await screen.findByRole("alert")).toHaveTextContent("copy it manually");
 c.rerender(<BootstrapHandoff username="other" publicKey={null} canGenerate={true} busy={false} generate={generate}/>);
 await user.click(screen.getByRole("button",{name:"Generate bootstrap key"}));expect(generate).toHaveBeenCalledTimes(1);
 expect(screen.queryByRole("status")).toBeNull();
 c.rerender(<BootstrapHandoff username="other" publicKey={null} canGenerate={true} busy={true} generate={generate}/>);
 expect(screen.getByRole("button",{name:"Preparing key…"})).toBeDisabled();
 c.rerender(<BootstrapHandoff username="other" publicKey={null} canGenerate={false} busy={false} generate={generate}/>);
 expect(screen.queryByRole("button",{name:"Generate bootstrap key"})).toBeNull();
 expect(screen.queryByLabelText(/Private key/i)).toBeNull();
});

import {fireEvent,render,screen,within} from "@testing-library/react";
import {describe,expect,it,vi} from "vitest";
import {adoptionChoice,ImportMembers} from "../src/ImportMembers";
import {ImportedAccess} from "../src/ImportedAccess";
import {review} from "./import-members.fixture";
import type {ImportedAccessView} from "../src/contracts";



// Full lifecycle consent and an exact eligible administrator owner are mandatory before submission.
describe("existing user adoption",()=>{
  it("rejects incomplete, duplicate and ineligible choices",()=>{
    expect(adoptionChoice(review,{},true)).toBeNull();
    expect(adoptionChoice(review,{"user-owner":"owner"},false)).toBeNull();
    expect(adoptionChoice(review,{"user-member":"owner"},true)).toBeNull();
    expect(adoptionChoice(review,{"user-owner":"member"},true)).toBeNull();
    expect(adoptionChoice(review,{"user-owner":"owner","user-member":"owner"},true)).toBeNull();
    expect(adoptionChoice(review,{"user-owner":"owner","user-member":"unknown"},true)).toBeNull();
    expect(adoptionChoice(review,{"user-owner":"owner","user-member":"member"},true)).toEqual({inventory_hash:review.inventory_hash,members:[{user_ocid:"user-owner",person_id:"owner"},{user_ocid:"user-member",person_id:"member"}],lifecycle_confirmed:true});
  });
  it("shows independent scopes, limits owner selection and emits exact choices",()=>{
    const change=vi.fn(),confirm=vi.fn(),refresh=vi.fn();
    const {rerender}=render(<ImportMembers review={review} selected={{"user-owner":"owner"}} confirmed={false} busy={false} change={change} confirm={confirm} refresh={refresh}/>);
    expect(screen.getByText("Root · shared root scope")).toBeInTheDocument();
    const selects=screen.getAllByRole("combobox");
    expect(within(selects[1]).getByRole("option",{name:/Accountable owner/})).toBeDisabled();
    fireEvent.change(selects[1],{target:{value:"member"}});
    expect(change).toHaveBeenCalledWith({"user-owner":"owner","user-member":"member"});
    fireEvent.click(screen.getByRole("checkbox"));expect(confirm).toHaveBeenCalledWith(true);
    fireEvent.click(screen.getByRole("button",{name:"Refresh existing users"}));expect(refresh).toHaveBeenCalledOnce();
    rerender(<ImportMembers review={{...review,inventory:{...review.inventory,users:[]}}} selected={{}} confirmed={false} busy={true} change={change} confirm={confirm} refresh={refresh}/>);
    expect(screen.getByText(/No existing accounts were verified/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
  it("keeps oversized adoption choices visible and blocked",()=>{
    const people=Array.from({length:51},(_,i)=>({id:String(i),name:`Person ${i}`,email:`person${i}@example.test`}));
    const users=people.map((person,i)=>({...review.inventory.users[0],user_ocid:`user-${i}`,scim_id:`scim-${i}`,email:person.email}));
    const large={...review,owner_person_id:"0",people,inventory:{...review.inventory,users}};
    const selected=Object.fromEntries(people.map((person,i)=>[`user-${i}`,person.id]));
    expect(adoptionChoice(large,selected,true)).toBeNull();
    render(<ImportMembers review={large} selected={selected} confirmed={true} busy={false} change={vi.fn()} confirm={vi.fn()} refresh={vi.fn()}/>);
    expect(screen.getByRole("alert")).toHaveTextContent("Select 50 or fewer");
    expect(screen.getAllByRole("combobox")).toHaveLength(51);
  });
  it("presents adopted access health independently with dated operation evidence",()=>{
    const navigate=vi.fn();
    const value:ImportedAccessView={state:"stale",checked_at:"2026-11-17T12:00:00Z",operation_id:"operation",members:[{association_id:"link",user_ocid:"user",user_name:"Existing member",state:"different"}],unmanaged_user_ocids:["outside-user"]};
    const {rerender}=render(<ImportedAccess value={value} navigate={navigate}/>);
    expect(screen.getByText(/Access changed \(earlier evidence\)/)).toBeInTheDocument();
    expect(screen.getByText("outside-user")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link",{name:"View check operation"}));expect(navigate).toHaveBeenCalled();
    for(const state of ["matching","drifted","unavailable","not_checked"] as const){rerender(<ImportedAccess value={{state}} navigate={navigate}/>);}
    rerender(<ImportedAccess value={{}} navigate={navigate}/>);expect(screen.getByText("Not checked")).toBeInTheDocument();
  });
});

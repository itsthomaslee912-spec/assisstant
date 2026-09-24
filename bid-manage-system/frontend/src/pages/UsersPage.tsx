import { useEffect, useState } from "react";
import { Button, Card, Col, Form, Input, InputNumber, Modal, Popconfirm, Row, Select, Space, Table, Tag, Typography, message } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { api } from "../api";
import type { Page, Profile, User } from "../types";

const EMPTY: Page<User> = {items:[],total:0,page:1,page_size:10};
export default function UsersPage({ currentUser }: { currentUser: User }) {
  const [data,setData]=useState(EMPTY), [profiles,setProfiles]=useState<Profile[]>([]), [page,setPage]=useState(1), [search,setSearch]=useState("");
  const [roleFilter,setRoleFilter]=useState("all"), [statusFilter,setStatusFilter]=useState("all"), [loading,setLoading]=useState(false);
  const [open,setOpen]=useState(false), [editing,setEditing]=useState<User|null>(null); const [form]=Form.useForm(); const role=Form.useWatch("role",form);
  const load=()=>{setLoading(true); api.users(new URLSearchParams({page:String(page),page_size:"10",search,role:roleFilter,status:statusFilter})).then(setData).catch(e=>message.error(e.message)).finally(()=>setLoading(false));};
  useEffect(load,[page,search,roleFilter,statusFilter]); useEffect(()=>{api.profileOptions().then(setProfiles).catch(e=>message.error(e.message));},[]);
  const edit=(user?:User)=>{setEditing(user||null);form.resetFields();form.setFieldsValue(user?{...user,password:"",profile_ids:user.profiles.map(p=>p.id)}:{role:"bidder",status:"active",profile_ids:[]});setOpen(true)};
  const save=async()=>{try{const values=await form.validateFields();if(editing&&!values.password)delete values.password;await api.saveUser(editing?.id||null,values);message.success(editing?"User updated":"User created");setOpen(false);load();}catch(e){if(e instanceof Error)message.error(e.message)}};
  return <div className="page-stack">
    <div className="page-heading"><div><Typography.Title level={2}>Users</Typography.Title><Typography.Text type="secondary">Manage access, bidder rates, wallets, and assigned profiles.</Typography.Text></div><Button type="primary" icon={<PlusOutlined/>} onClick={()=>edit()}>New user</Button></div>
    <Card className="content-card"><div className="table-toolbar multi"><Input allowClear prefix={<SearchOutlined/>} placeholder="Search email, user ID, or wallet" value={search} onChange={e=>{setPage(1);setSearch(e.target.value)}}/><Select value={roleFilter} onChange={v=>{setPage(1);setRoleFilter(v)}} options={[{value:"all",label:"All roles"},{value:"admin",label:"Admin"},{value:"bidder",label:"Bidder"}]}/><Select value={statusFilter} onChange={v=>{setPage(1);setStatusFilter(v)}} options={[{value:"all",label:"All statuses"},{value:"active",label:"Active"},{value:"deactive",label:"Deactive"}]}/></div>
      <Table rowKey="id" loading={loading} dataSource={data.items} scroll={{x:950}} pagination={{current:page,pageSize:10,total:data.total,showTotal:n=>`${n} users`,onChange:setPage}} columns={[
        {title:"User",render:(_,r)=><strong>{r.user_id}</strong>},{title:"Role",dataIndex:"role",render:v=><Tag color={v==="admin"?"purple":"blue"}>{v.toUpperCase()}</Tag>},{title:"Status",dataIndex:"status",render:v=><Tag color={v==="active"?"green":"red"}>{v}</Tag>},
        {title:"Assigned profiles",render:(_,r)=>r.role==="admin"?"—":r.profiles.map(p=>`${p.first_name} ${p.last_name}`).join(", ")||"None"},{title:"Rate",render:(_,r)=>r.role==="bidder"?`$${Number(r.per_bid_pay_amount||0).toFixed(2)}`:"—"},
        {title:"Actions",fixed:"right",render:(_,r)=><Space><Button icon={<EditOutlined/>} onClick={()=>edit(r)}/><Popconfirm disabled={r.id===currentUser.id} title="Delete this user?" onConfirm={()=>api.deleteUser(r.id).then(load).catch(e=>message.error(e.message))}><Button disabled={r.id===currentUser.id} danger icon={<DeleteOutlined/>}/></Popconfirm></Space>}
      ]}/>
    </Card>
    <Modal open={open} title={editing?"Edit user":"Create user"} onCancel={()=>setOpen(false)} onOk={save} okText={editing?"Save changes":"Create user"} destroyOnHidden>
      <Form form={form} layout="vertical"><Row gutter={16}><Col span={12}><Form.Item name="user_id" label="User ID" rules={[{required:true,min:3}]}><Input/></Form.Item></Col><Col span={12}><Form.Item name="email" label="Email" rules={[{required:true,type:"email"}]}><Input/></Form.Item></Col></Row>
        <Form.Item name="password" label={editing?"New password (optional)":"Password"} rules={editing?[]:[{required:true,min:8}]}><Input.Password/></Form.Item>
        <Row gutter={16}><Col span={12}><Form.Item name="role" label="Role" rules={[{required:true}]}><Select options={[{value:"admin",label:"Admin"},{value:"bidder",label:"Bidder"}]}/></Form.Item></Col><Col span={12}><Form.Item name="status" label="Status" rules={[{required:true}]}><Select options={[{value:"active",label:"Active"},{value:"deactive",label:"Deactive"}]}/></Form.Item></Col></Row>
        {role==="bidder"&&<><Row gutter={16}><Col span={12}><Form.Item name="per_bid_pay_amount" label="Per-bid pay amount" rules={[{required:true}]}><InputNumber prefix="$" min={0} precision={2} style={{width:"100%"}}/></Form.Item></Col><Col span={12}><Form.Item name="crypto_address" label="Crypto address" rules={[{required:true}]}><Input/></Form.Item></Col></Row><Form.Item name="profile_ids" label="Assigned profiles"><Select mode="multiple" optionFilterProp="label" options={profiles.map(p=>({value:p.id,label:`${p.first_name} ${p.last_name} · ${p.email}`}))}/></Form.Item></>}
      </Form>
    </Modal>
  </div>;
}

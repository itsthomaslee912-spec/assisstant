import { useEffect, useState } from "react";
import dayjs from "dayjs";
import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Row, Select, Space, Table, Tag, Typography, Upload, message } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import { api } from "../api";
import type { Page, Profile } from "../types";

const EMPTY: Page<Profile> = { items: [], total: 0, page: 1, page_size: 10 };
const fields: Array<[string,string,number?]> = [
  ["phone_number","Phone Number"],["linkedin","LinkedIn"],["github","GitHub"],["personal_website","Personal website"],
  ["portfolio","Portfolio"],["street","Street",24],["city","City"],["state","State"],["zipcode","Zipcode"],
  ["current_company","Current Company"],["origin_ethnicity","Origin or Ethnicity"],["university","University"],
  ["degree","Degree"],["major","Major"],["duration","Duration"],["availability","Availability"]
];

export default function ProfilesPage() {
  const [data, setData] = useState(EMPTY), [page, setPage] = useState(1), [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false), [open, setOpen] = useState(false), [editing, setEditing] = useState<Profile | null>(null);
  const [resume, setResume] = useState<File | null>(null); const [form] = Form.useForm();
  const load = () => { setLoading(true); api.profiles(new URLSearchParams({page:String(page),page_size:"10",search})).then(setData).catch((e)=>message.error(e.message)).finally(()=>setLoading(false)); };
  useEffect(load, [page, search]);
  const edit = (record?: Profile) => { setEditing(record || null); setResume(null); form.resetFields(); if(record) form.setFieldsValue({...record,date_of_birth:record.date_of_birth?dayjs(record.date_of_birth):null}); setOpen(true); };
  const save = async () => { try { const values=await form.validateFields(); const body={...values,date_of_birth:values.date_of_birth?.format("YYYY-MM-DD")||null}; const profile=await api.saveProfile(editing?.id||null,body); if(resume) await api.uploadResume(profile.id,resume); message.success(editing?"Profile updated":"Profile created"); setOpen(false); load(); } catch(e) { if(e instanceof Error) message.error(e.message); } };
  return <div className="page-stack">
    <div className="page-heading"><div><Typography.Title level={2}>Profiles</Typography.Title><Typography.Text type="secondary">Manage candidate details, eligibility, education, and resumes.</Typography.Text></div><Button type="primary" icon={<PlusOutlined/>} onClick={()=>edit()}>New profile</Button></div>
    <Card className="content-card"><div className="table-toolbar"><Input allowClear prefix={<SearchOutlined/>} placeholder="Search name, email, or company" value={search} onChange={(e)=>{setPage(1);setSearch(e.target.value)}} /></div>
      <Table rowKey="id" loading={loading} dataSource={data.items} scroll={{x:900}} pagination={{current:page,pageSize:10,total:data.total,showTotal:(n)=>`${n} profiles`,onChange:setPage}} columns={[
        {title:"Candidate",render:(_,r)=><div><strong>{r.first_name} {r.last_name}</strong><div className="muted">{r.email}</div></div>},
        {title:"Location",render:(_,r)=>[r.city,r.state].filter(Boolean).join(", ")||"—"},{title:"Company",dataIndex:"current_company",render:(v)=>v||"—"},
        {title:"Availability",dataIndex:"availability",render:(v)=><Tag color={v?"blue":"default"}>{v||"Not set"}</Tag>},
        {title:"Resume",dataIndex:"resume_path",render:(v)=>v?<Tag color="green">Uploaded</Tag>:<Tag>Missing</Tag>},
        {title:"Actions",fixed:"right",render:(_,r)=><Space><Button icon={<EditOutlined/>} onClick={()=>edit(r)}/><Popconfirm title="Delete this profile?" onConfirm={()=>api.deleteProfile(r.id).then(load).catch(e=>message.error(e.message))}><Button danger icon={<DeleteOutlined/>}/></Popconfirm></Space>}
      ]}/>
    </Card>
    <Modal width={920} open={open} title={editing?"Edit profile":"Create profile"} onCancel={()=>setOpen(false)} onOk={save} okText={editing?"Save changes":"Create profile"} destroyOnHidden>
      <Form form={form} layout="vertical" className="profile-form" initialValues={{phone_number:"",race:"",asian_region:"",gender:"",visa_status:"",veteran_status:"",disability_status:""}}>
        <Typography.Title level={5}>Personal details</Typography.Title><Row gutter={16}>
          <Col xs={24} md={8}><Form.Item name="first_name" label="First Name" rules={[{required:true}]}><Input/></Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="last_name" label="Last Name" rules={[{required:true}]}><Input/></Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="email" label="Email" rules={[{required:true,type:"email"}]}><Input/></Form.Item></Col>
          {fields.slice(0,5).map(([name,label])=><Col xs={24} md={8} key={name}><Form.Item name={name} label={label}><Input/></Form.Item></Col>)}
          <Col xs={24} md={8}><Form.Item name="date_of_birth" label="Date of Birth"><DatePicker style={{width:"100%"}}/></Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="salary" label="Salary"><InputNumber min={0} prefix="$" style={{width:"100%"}}/></Form.Item></Col>
        </Row>
        <Typography.Title level={5}>Demographics and eligibility</Typography.Title><Row gutter={16}>
          <Col xs={24} md={8}><Form.Item name="race" label="Race"><Input/></Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="asian_region" label="If Asian"><Select allowClear options={["East Asian","South Asian","Southeast Asian"].map(value=>({value}))}/></Form.Item></Col>
          {[["gender","Gender"],["visa_status","Visa Status"],["veteran_status","Veteran Status"],["disability_status","Disability Status"]].map(([name,label])=><Col xs={24} md={8} key={name}><Form.Item name={name} label={label}><Input/></Form.Item></Col>)}
          <Col xs={24} md={8}><Form.Item name="origin_ethnicity" label="Origin or Ethnicity"><Input/></Form.Item></Col>
        </Row>
        <Typography.Title level={5}>Address, education and work</Typography.Title><Row gutter={16}>{fields.slice(5).map(([name,label,span])=><Col xs={24} md={span||8} key={name}><Form.Item name={name} label={label}><Input/></Form.Item></Col>)}</Row>
        <Form.Item label="Resume"><Upload maxCount={1} beforeUpload={(file)=>{setResume(file);return false}} accept=".pdf,.doc,.docx"><Button icon={<UploadOutlined/>}>Choose resume</Button></Upload>{editing?.resume_path&&<Typography.Text type="secondary"> Current resume is saved.</Typography.Text>}</Form.Item>
      </Form>
    </Modal>
  </div>;
}


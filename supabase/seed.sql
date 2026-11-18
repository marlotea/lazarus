-- Default workspace for v0 (single user). The backend reads its id at startup.
insert into workspaces (name) values ('cpsc-448')
on conflict (name) do nothing;

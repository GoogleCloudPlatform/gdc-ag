Clone the workshop repo from GitHub.

Download the GDCloud toolkit from the GDC Console.

Validate Landing Zone config on `projects_config.yaml`.

Scripts:

0. Run `./000-install-gdcloud.sh` to install GDCloud toolkit.

1. Run `./001-create-projects.py` to create your workloads Project.

2. Run `./002-apply-role-bindings.py` to create your users and apply role bindings to your project.

3. Run `./003-createharborproject.sh` to create your project on the Harbor Instance.

Log into Harbor, generate a user secret.

4. Run `./004-addharborsecret.sh` to create docker registry secret.


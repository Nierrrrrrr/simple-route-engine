#!/usr/bin/env python3
"""Render an undeployed template; never reads kube contexts or applies manifests."""
import json,pathlib,re,sys
assert len(sys.argv)==4,'namespace image@sha256:digest output.json'
namespace,image,dest=sys.argv[1:]
assert re.fullmatch('[a-z0-9][a-z0-9-]{0,62}',namespace)
assert re.fullmatch('[a-z0-9./:_-]+@sha256:[a-f0-9]{64}',image)
p=pathlib.Path(__file__).resolve().parents[1]/'config/deployment/app.template.json'
body=p.read_text().replace('ROUTE_NAMESPACE',namespace).replace('ROUTE_IMAGE_DIGEST',image)
json.loads(body);pathlib.Path(dest).write_text(body)

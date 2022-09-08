from quart import Blueprint, request, redirect, render_template
from io import BytesIO
import base64
import torch
import impaintingLib as imp
import numpy as np
from torchvision import transforms
from PIL import Image, ImageChops
from datetime import datetime
import json

import impaintingLib as imp
from impaintingLib.model import keypoint

# ---------------

impBP = Blueprint('imp', __name__, template_folder='templates', static_folder='static')

# ---------------

factorResize = 2
scale_factor = 2

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Impainter
impainter = imp.model.UNet(5, netType="partial")
impainter_weight_path = './modelSave/impainter.pth'
impainter.load_state_dict(torch.load(impainter_weight_path, map_location=device))
impainter.eval()

# Classifier
classifier_weight_path = "./modelSave/classifierUNet.pth"
classif = imp.model.ClassifierUNet()
classif.load_state_dict(torch.load(classifier_weight_path,map_location=device))
classif.eval()

# ---------------


def convertImage(image,doCrop=True):
    w,h = image.size
    resize = (120*factorResize, 120*factorResize)
    crop   = (64*factorResize, 64*factorResize)

    if doCrop : 
        process = transforms.Compose([
            transforms.Resize(resize), 
            transforms.CenterCrop(crop),
            transforms.ToTensor()
    ])
    else : 
        process = transforms.Compose([
            transforms.Resize(crop), 
            transforms.ToTensor()
    ])

    image = process(image)
    c,w,h = image.shape
    image = image.view(1,c,w,h)
    return image

def segment(image):
    with torch.no_grad():
        if scale_factor > 0 :
            image = torch.nn.functional.interpolate(image, scale_factor=scale_factor)
        normalized = transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))(image)
        classifiedImage = classif(normalized)
        # classifiedImage = torch.nn.functional.avg_pool2d(classifiedImage, scale_factor)
        _,_,w,_ = classifiedImage.shape
        classifPlain = imp.loss.generate_label_plain(classifiedImage,w)
        classifPlain = imp.components.simplifyChannels(classifPlain)
        classifPlain = (classifPlain + 1) * 25
        classifPlain = classifPlain.astype(np.uint8)
        pil_image = Image.fromarray(classifPlain[0])
    return pil_image

def impaint(mask,segmented,enhance,keypoints,modelOpt):
    image = Image.open("./impaintingWeb/static/image/original.jpg")
    image   = convertImage(image)
    mask    = convertImage(mask)
    segmented = convertImage(segmented,doCrop=False)

    segmented = segmented * 255
    segmented = (segmented / 25) - 1
    segmented = torch.round(segmented)
    segmented = (segmented / 9) + 0.1

    mask = (mask < 0.5) * 1.
    x_prime = imp.mask.propagate(image,mask)

    x_prime2 = torch.cat((x_prime,segmented),dim=1)
    keypointLayer = imp.components.addKeypoints(image, keypoints)
    x_prime3 = torch.cat((x_prime2, keypointLayer),dim=1)

    with torch.no_grad():

        if modelOpt == "default" : 
            image_hat = impainter(x_prime3)
        else : 
            print("Error no model found")
            image_hat = x_prime3
            
        image_hat = torch.clip(image_hat,0,1)[:,:3]
        if enhance : 
            image_hat = imp.components.superRes(image_hat)

    image_hat = transforms.ToPILImage()(image_hat[0])
    return image_hat

# ---------------

@impBP.route("/")
async def home():
    return await render_template('home.html')

# Recevoir l'image encodé en Base 64
# Générer la segmentation et croper/resizer au bon format
# Stocker ces informations sous forme d'image
# Générer les keypoints et les envoyer en réponse sous forme de liste  
@impBP.route("/segment", methods=['POST'])
async def segmentPOST():
    ask        = await request.form
    dataB64    = ask["imgB64"]
    img = Image.open(BytesIO(base64.b64decode(dataB64))).convert('RGB')
    img.save("./impaintingWeb/static/image/original.jpg")
    
    original_crop = convertImage(img)
    segmented = segment(original_crop)
    segmented.save("./impaintingWeb/static/image/mask.jpg")

    keypoints = imp.components.getLandmarks(original_crop)[0]
    keypoints = keypoints.tolist()

    original_crop = transforms.ToPILImage()(original_crop[0])
    original_crop.save("./impaintingWeb/static/image/original_crop.jpg")

    return {"keypoints" : keypoints}

# Recevoir masques, segementation, keypoints et choix sur la super résolution
# Convertir les informations reçues au bon format
# Faire la prédiction et la sauvegarder
@impBP.route("/predict", methods=['POST'])
async def predictPOST():
    ask        = await request.form
    maskB64    = ask["maskB64"]
    segmentB64 = ask["segmentB64"]
    doEnhance  = ask["doEnhance"]
    modelOpt   = ask["modelOpt"]
    keypoints  = ask["keypoints"]
    doEnhance = doEnhance == "true" 

    mask = Image.open(BytesIO(base64.b64decode(maskB64)))
    mask.load() # required for png.split()
    maskRGB = Image.new("RGB", mask.size, (255, 255, 255))

    maskRGB.paste(mask, mask=mask.split()[3]) # 3 is the alpha channel
    mask = maskRGB.convert("L")
    segment = Image.open(BytesIO(base64.b64decode(segmentB64))).convert("L")

    keypoints = json.loads(keypoints)
    keypoints = torch.Tensor(keypoints)
    keypoints = torch.unsqueeze(keypoints, dim=0)

    predict = impaint(mask,segment,doEnhance,keypoints,modelOpt)
    predict.save("./impaintingWeb/static/image/predict.jpg")
    return {"ok" : True}

# Recevoir le masque et la segmentation
# Les télécharger
@impBP.route("/download", methods=['POST'])
async def download():
    ask        = await request.form
    maskB64    = ask["maskB64"]
    segmentB64 = ask["segmentB64"]

    mask = Image.open(BytesIO(base64.b64decode(maskB64)))
    mask.load() # required for png.split()
    maskRGB = Image.new("RGB", mask.size, (255, 255, 255))
    maskRGB.paste(mask, mask=mask.split()[3]) # 3 is the alpha channel
    mask = maskRGB.convert("L")
    segment = Image.open(BytesIO(base64.b64decode(segmentB64))).convert("L")

    mask.save("./impaintingWeb/static/image/downloaded/mask.jpg")
    segment.save("./impaintingWeb/static/image/downloaded/seg.jpg")
    return {"ok" : True}
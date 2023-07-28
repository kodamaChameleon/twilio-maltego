import trio
from maltego_trx.maltego import MaltegoTransform, MaltegoMsg
from maltego_trx.transform import DiscoverableTransform
from extensions import registry, twilio_set
from twilio.rest import Client
import csv

def read_account_credentials():
    try:
        with open(".key", "r") as file:
            credentials = file.readlines()

        account_sid = None
        auth_token = None

        for line in credentials:
            key, value = line.strip().split('=')
            if key == "ACCOUNT_SID":
                account_sid = value
            elif key == "AUTH_TOKEN":
                auth_token = value

        if account_sid and auth_token:
            return account_sid, auth_token
        else:
            print("Failed to read account credentials from creds.key.")
    except Exception as e:
        print(f"An error occurred while reading the credentials: {e}")

def activity_phone_lookup(account_sid: str, auth_token: str, phone_number: str):
    client = Client(account_sid, auth_token)
    response = client.lookups.v2.phone_numbers(phone_number).fetch(fields='live_activity')

    return response

def get_country_data(country_code):
    try:
        with open('country_data.csv', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['alpha-2'].lower() == country_code.lower():
                    return row
        return None
    except Exception as e:
        print(f"An error occurred while reading the CSV file: {e}")
        return None

@registry.register_transform(
    display_name="Get date of last SIM swap [twilio] (Special Access Required)", 
    input_entity="maltego.PhoneNumber",
    description='Returns details from Twilio API lookup for SIM swap ($/lookup)', #Requires package authorization. Submit form at https://twlo.my.salesforce-sites.com/countrycarrier/SN_CarrierRegistration_VFP
    settings=[],
    output_entities=["maltego.Unknown"],
    transform_set=twilio_set
    )
class checkActivity(DiscoverableTransform):
    
    @classmethod
    def create_entities(cls, request: MaltegoMsg, response: MaltegoTransform):

        async def main():

            # Retrieve number from entity
            phone_number = request.Value

            # Perform Twilio API lookup using stored credentials
            account_sid, auth_token = read_account_credentials()
            lookup = activity_phone_lookup(account_sid, auth_token, phone_number)

            # Convert results to entities
            if lookup.valid == True:
                number = response.addEntity("maltego.PhoneNumber", value = lookup.phone_number)
                number.addProperty("Valid", value = "True")
                number.addProperty("Connectivity", value = lookup.live_activity["connectivity"])
                response.addEntity("maltego.Organization", value = lookup.live_activity["original_carrier"]["name"])
                if lookup.live_activity["ported"] == "true":
                    response.addEntity("maltego.Organization", value = lookup.live_activity["ported_carrier"])
                if lookup.live_activity["roaming"] == "true":
                    response.addEntity("maltego.Organization", value = lookup.live_activity["roaming_carrier"])

                if lookup.live_activity["original_carrier"]["mobile_country_code"]:
                    response.addEntity("maltego.AS", value = "MCC# " + str(lookup.live_activity["original_carrier"]["mobile_country_code"]))
                if lookup.live_activity["original_carrier"]["mobile_network_code"]:
                    response.addEntity("maltego.AS", value = "MNC# " + str(lookup.live_activity["original_carrier"]["mobile_network_code"]))

                # Enrich country code data
                country_data = get_country_data(lookup.country_code)
                country = response.addEntity("maltego.Country", value = country_data["name"])
                country.addProperty("location.area", value = country_data["sub-region"])
                country.addProperty("location.areacode", value = country_data["sub-region-code"])
                country.addProperty("countrycode", value = country_data["alpha-2"])
            else:
                response.addEntity("maltego.Phrase", value = "Invalid Number")

        trio.run(main) # running our async code in a non-async code
"""The demo catalogue: five Caribbean countries.

Place names are real (beaches, waterfalls, forts, parks, markets); every business
(guesthouse, restaurant, tour company) and every price is invented for the demo.

Compact rows are turned into database rows by `seed_catalogue`. Area keys are unique across
all countries, so each row says exactly where it is.
"""

from datetime import time

from .models import Activity, ActivityStart, ActivityTag, Area, Destination, Restaurant, Stay


def t(text):
    h, m = text.split(":")
    return time(int(h), int(m))


# code, name, blurb
DESTINATIONS = [
    ("VC", "St Vincent and the Grenadines", "A green volcanic main island and a string of small sailing islands to the south."),
    ("BB", "Barbados", "Calm west-coast sea, wild Atlantic east coast, and a capital that's a World Heritage Site."),
    ("LC", "St Lucia", "The Pitons, rainforest, a drive-in volcano and busy beaches in the north."),
    ("GD", "Grenada", "The spice island: nutmeg, waterfalls and one of the Caribbean's best beaches."),
    ("DM", "Dominica", "The nature island: rainforest, hot springs, waterfalls and some of the best diving around."),
]

# destination, key, name, island, lat, lng
AREAS = [
    ("VC", "kingstown", "Kingstown", "St Vincent", 13.155, -61.227),
    ("VC", "villa", "Villa and Indian Bay", "St Vincent", 13.132, -61.199),
    ("VC", "leeward", "Leeward coast", "St Vincent", 13.247, -61.268),
    ("VC", "windward", "Georgetown and La Soufrière", "St Vincent", 13.282, -61.118),
    ("VC", "bequia", "Bequia", "Bequia", 13.007, -61.239),
    ("BB", "bridgetown", "Bridgetown", "Barbados", 13.097, -59.613),
    ("BB", "west", "West coast (Holetown)", "Barbados", 13.186, -59.637),
    ("BB", "south", "South coast (Oistins)", "Barbados", 13.064, -59.540),
    ("BB", "east", "East coast (Bathsheba)", "Barbados", 13.214, -59.523),
    ("LC", "castries", "Castries", "St Lucia", 14.010, -60.990),
    ("LC", "rodney", "Rodney Bay and Gros Islet", "St Lucia", 14.077, -60.952),
    ("LC", "marigot", "Marigot Bay", "St Lucia", 13.966, -61.025),
    ("LC", "soufriere", "Soufrière and the Pitons", "St Lucia", 13.856, -61.057),
    ("GD", "stgeorges", "St George's", "Grenada", 12.056, -61.752),
    ("GD", "grandanse", "Grand Anse", "Grenada", 12.022, -61.763),
    ("GD", "interior", "Grand Etang rainforest", "Grenada", 12.095, -61.695),
    ("GD", "north", "Gouyave and the north", "Grenada", 12.165, -61.729),
    ("DM", "roseau", "Roseau", "Dominica", 15.301, -61.388),
    ("DM", "valley", "Roseau Valley", "Dominica", 15.318, -61.338),
    ("DM", "scotts", "Soufrière and Scotts Head", "Dominica", 15.215, -61.365),
    ("DM", "portsmouth", "Portsmouth", "Dominica", 15.578, -61.457),
]

# area, name, style, US$ a night, sleeps, rooms, kid friendly, step free, free-cancel hours, blurb
STAYS = [
    ("kingstown", "Breadfruit Guesthouse", "guesthouse", 75, 2, 6, True, False, 24, "Family-run rooms above the town, with a breezy shared veranda."),
    ("villa", "Indian Bay Inn", "hotel", 165, 3, 18, True, True, 48, "Sea-view rooms a short walk from the beach, with a pool."),
    ("villa", "Blue Lantern House", "boutique", 240, 2, 8, False, False, 72, "Eight quiet rooms in a restored stone house over Villa Bay."),
    ("bequia", "Friendship Point Villas", "villa", 310, 6, 3, True, False, 72, "Three-bedroom villas with kitchens and a view of Admiralty Bay."),
    ("bequia", "Admiralty Sands Resort", "resort", 420, 3, 30, True, True, 72, "Beachfront resort with a pool, kids' club and water sports."),
    ("bridgetown", "Pelican Lane Guesthouse", "guesthouse", 85, 2, 8, True, False, 24, "Simple, spotless rooms near the boardwalk and the bus terminal."),
    ("south", "Seagate Hotel", "hotel", 190, 3, 40, True, True, 48, "Mid-size hotel on the south coast with a pool and a reef out front."),
    ("west", "Coral Lantern Boutique Hotel", "boutique", 330, 2, 12, False, True, 72, "Twelve calm rooms right on the sand at Holetown."),
    ("west", "Sandalwood Bay Resort", "resort", 520, 3, 60, True, True, 72, "Big beach, three pools, kids' club and a spa."),
    ("east", "Cattlewash Cottages", "villa", 260, 6, 3, True, False, 72, "Cottages with kitchens above the wild Atlantic coast."),
    ("castries", "Morne View Guesthouse", "guesthouse", 80, 2, 7, True, False, 24, "Hillside rooms with a view over the harbour."),
    ("rodney", "Reduit Palms Hotel", "hotel", 185, 3, 50, True, True, 48, "A short walk to Reduit Beach and Rodney Bay's restaurants."),
    ("marigot", "Hummingbird Bay Boutique", "boutique", 340, 2, 10, False, False, 72, "Ten rooms on the hillside above Marigot Bay's lagoon."),
    ("soufriere", "Twin Peaks Resort", "resort", 560, 3, 40, True, True, 72, "Pitons on one side, sea on the other, with a spa and pools."),
    ("rodney", "Gros Islet Garden Villas", "villa", 280, 6, 4, True, False, 72, "Villas with kitchens and a shared pool near the beach."),
    ("stgeorges", "Carenage Rooms", "guesthouse", 70, 2, 8, True, False, 24, "Rooms in a stone warehouse on the Carenage."),
    ("grandanse", "Morne Rouge Hotel", "hotel", 175, 3, 36, True, True, 48, "Across the road from Grand Anse beach, with a pool."),
    ("grandanse", "Cinnamon Cove Boutique", "boutique", 310, 2, 9, False, False, 72, "Nine rooms in a garden above a quiet cove."),
    ("grandanse", "Spice Coast Resort", "resort", 480, 3, 55, True, True, 72, "On Grand Anse beach, with a spa and kids' club."),
    ("north", "Nutmeg Ridge Villas", "villa", 230, 6, 3, True, False, 72, "Villas with kitchens in the hills above Gouyave."),
    ("roseau", "Bayfront Guesthouse", "guesthouse", 70, 2, 9, True, False, 24, "Plain, friendly rooms on Roseau's seafront."),
    ("roseau", "Fort Young Garden Hotel", "hotel", 165, 3, 30, True, True, 48, "A comfortable base in town with a pool by the sea."),
    ("valley", "Wotten Waven Eco Lodge", "boutique", 260, 2, 10, False, False, 72, "Cabins in the rainforest with hot-spring baths."),
    ("scotts", "Scotts Head Dive Resort", "resort", 390, 3, 28, True, True, 72, "Dive centre, pool and a reef straight off the jetty."),
    ("portsmouth", "Prince Rupert Bay Villas", "villa", 210, 6, 3, True, False, 72, "Villas with kitchens above a long, calm bay."),
]

# area, name, tags, minutes, US$ adult, US$ child, energy, min age, step free, best time,
# opens, closes, closed days, flags (lunch / dinner = the meal is part of it, star = local favourite),
# set start times ("" = whenever you like), capacity per start (None = no booking), blurb
ACTIVITIES = [
    # ---- St Vincent and the Grenadines
    ("kingstown", "Fort Charlotte and the view over Kingstown", "culture", 90, 5, 2, 1, 0, False, "morning", "08:00", "17:00", "", "star", "", None, "An 1806 fort 200 m above the sea, with views to the Grenadines."),
    ("kingstown", "Botanic Gardens", "nature culture", 90, 5, 2, 1, 0, True, "morning", "08:00", "17:00", "", "", "", None, "The oldest botanic gardens in the Americas, with a breadfruit tree from Captain Bligh's voyage."),
    ("kingstown", "Kingstown market morning", "shopping food", 75, 0, 0, 1, 0, True, "morning", "07:00", "14:00", "6", "", "", None, "Fruit, fish and spices from all over the island. Busiest on Fridays and Saturdays."),
    ("kingstown", "Vincy cooking class", "food culture", 180, 85, 45, 1, 6, True, "afternoon", "10:00", "18:00", "06", "", "14:00", 10, "Cook roast breadfruit, fried jackfish and callaloo soup, then eat it all."),
    ("windward", "La Soufrière volcano hike", "hiking adventure nature", 360, 70, 50, 3, 10, False, "morning", "06:00", "15:00", "", "star lunch", "07:00", 12, "Climb through rainforest to the rim of an active volcano's crater. Guide and packed lunch included."),
    ("windward", "Owia salt pond swim", "beaches nature", 120, 3, 1, 1, 0, False, "afternoon", "08:00", "17:00", "", "", "", None, "Natural rock pools filled by Atlantic waves at the island's northern tip."),
    ("leeward", "Dark View Falls", "nature hiking", 120, 5, 2, 2, 4, False, "any", "08:00", "17:00", "", "star", "", None, "Two waterfalls reached over a bamboo bridge, with a cool pool to swim in."),
    ("leeward", "Vermont Nature Trail parrot walk", "nature hiking", 150, 5, 2, 2, 6, False, "morning", "06:30", "16:00", "", "", "", None, "A rainforest loop where you may spot the St Vincent parrot, best early."),
    ("leeward", "Wallilabou Bay snorkel and swim", "beaches water", 150, 10, 5, 1, 4, False, "afternoon", "09:00", "17:30", "", "", "", None, "A sheltered bay on the leeward coast with snorkelling off the rocks."),
    ("villa", "Indian Bay snorkel", "water beaches", 120, 15, 10, 1, 6, False, "morning", "08:00", "17:00", "", "", "", None, "Easy reef snorkelling just off the beach, with gear to rent on the sand."),
    ("villa", "Stand-up paddleboard lesson", "water adventure", 90, 45, 35, 2, 10, False, "morning", "08:00", "16:00", "", "", "09:00 14:00", 8, "Learn on the calm water of Villa Bay with Calliaqua Paddle Co."),
    ("villa", "Breadnut Spa afternoon", "wellness", 120, 95, 95, 1, 16, True, "afternoon", "10:00", "19:00", "6", "", "", None, "Massage and a garden plunge pool overlooking Young Island."),
    ("villa", "Friday night lime at Villa", "nightlife food", 180, 0, 0, 1, 0, False, "evening", "19:00", "23:59", "012356", "dinner", "", None, "Music, grilled fish and dancing along the Villa waterfront, on Fridays."),
    ("bequia", "Princess Margaret Beach", "beaches", 180, 0, 0, 1, 0, False, "any", "07:00", "18:00", "", "star", "", None, "A long, calm curve of sand with snorkelling at its southern end."),
    ("bequia", "Tobago Cays sailing day", "water beaches nature", 480, 160, 90, 2, 5, False, "morning", "08:00", "17:00", "", "star lunch", "08:30", 20, "Sail to the Tobago Cays to swim with turtles. Lunch on board, with Grenadines Day Sails."),
    ("bequia", "Moonhole walk", "hiking culture", 150, 0, 0, 2, 8, False, "morning", "07:00", "16:00", "", "", "", None, "Walk out to the hand-built stone houses at Moonhole, on Bequia's wild south-west tip."),
    ("bequia", "Bequia sunset sail", "water nightlife", 120, 70, 40, 1, 4, False, "evening", "16:30", "19:00", "", "", "16:30", 16, "Two hours under sail around Admiralty Bay as the sun goes down."),
    ("bequia", "Model boat workshops", "culture shopping", 60, 0, 0, 1, 0, True, "afternoon", "09:00", "16:30", "6", "", "", None, "Watch Bequia's famous model boats being carved and painted by hand."),
    # ---- Barbados
    ("bridgetown", "Historic Bridgetown and Garrison walk", "culture", 150, 25, 10, 1, 0, True, "morning", "08:30", "17:00", "6", "star", "09:00 14:00", 15, "A guided walk round the World Heritage town and its military Garrison."),
    ("bridgetown", "Carlisle Bay turtles and wrecks", "water beaches", 150, 75, 50, 1, 6, False, "morning", "08:00", "16:00", "", "star", "09:30 13:30", 24, "Snorkel over shipwrecks and swim with turtles, with Pelican Snorkel Tours."),
    ("bridgetown", "Cheapside market and rum shops", "shopping food culture", 120, 0, 0, 1, 0, True, "morning", "07:00", "15:00", "6", "", "", None, "Saturday market produce, then a look into the little rum shops nearby."),
    ("bridgetown", "Bajan cooking class", "food culture", 180, 90, 45, 1, 6, True, "afternoon", "10:00", "18:00", "06", "", "14:00", 10, "Make flying fish, cou-cou and macaroni pie, then sit down to eat it."),
    ("west", "West coast catamaran day", "water beaches", 300, 120, 70, 1, 3, False, "morning", "09:00", "15:30", "", "star lunch", "09:30", 40, "Sail the calm west coast, snorkel with turtles, lunch and drinks on board."),
    ("west", "Folkestone Marine Park snorkel", "water nature", 120, 10, 5, 1, 5, False, "any", "08:00", "17:00", "", "", "", None, "A protected reef close to the shore at Holetown."),
    ("west", "Holetown shops and the first settlement", "shopping culture", 90, 0, 0, 1, 0, True, "afternoon", "09:00", "17:00", "6", "", "", None, "Where English settlers landed in 1627, now boutiques and a sleepy church."),
    ("west", "Coral Sands spa", "wellness", 120, 140, 140, 1, 16, True, "afternoon", "10:00", "19:00", "", "", "", None, "Treatments in a garden spa a few steps from the sea."),
    ("south", "Oistins Friday fish fry", "food nightlife culture", 180, 0, 0, 1, 0, True, "evening", "18:30", "23:59", "012356", "star dinner", "", None, "Grilled fish, music and dancing in the fishing village, every Friday night."),
    ("south", "Surf lesson at Freights Bay", "adventure water", 120, 80, 60, 2, 8, False, "morning", "08:00", "15:00", "", "", "08:30 13:00", 8, "Gentle waves for a first surf, with Freights Bay Surf School."),
    ("south", "St Lawrence Gap night out", "nightlife food", 150, 0, 0, 1, 18, False, "evening", "20:30", "23:59", "", "", "", None, "The south coast's strip of bars and live music."),
    ("south", "Crane Beach", "beaches", 180, 0, 0, 1, 0, False, "any", "07:00", "18:00", "", "", "", None, "Pink-tinged sand under cliffs, with bodysurfing waves."),
    ("east", "Bathsheba and the Soup Bowl", "nature beaches", 120, 0, 0, 1, 0, False, "morning", "07:00", "18:00", "", "star", "", None, "Giant boulders on the Atlantic shore and one of the world's famous surf breaks."),
    ("east", "Old railway trail hike", "hiking nature", 180, 0, 0, 2, 8, False, "morning", "06:30", "16:00", "", "", "", None, "Follow the old railway line along the east coast from Bath to Bathsheba."),
    ("east", "Coral Reef Rum House tasting", "food culture", 90, 35, 0, 1, 18, True, "afternoon", "10:00", "17:00", "6", "", "11:00 14:00 15:30", 20, "A small family distillery's tour and tasting."),
    # ---- St Lucia
    ("rodney", "Pigeon Island National Park", "culture hiking beaches", 180, 10, 4, 2, 0, False, "morning", "09:00", "17:00", "", "star", "", None, "Fort ruins, two short summit climbs and a beach to finish."),
    ("rodney", "Reduit Beach", "beaches water", 180, 0, 0, 1, 0, True, "any", "07:00", "18:30", "", "", "", None, "A long, calm beach with water sports to rent."),
    ("rodney", "Gros Islet Friday street party", "nightlife food culture", 210, 0, 0, 1, 0, False, "evening", "19:00", "23:59", "012356", "star dinner", "", None, "Street food, sound systems and dancing in the village every Friday."),
    ("rodney", "Rodney Bay marina shops", "shopping", 90, 0, 0, 1, 0, True, "afternoon", "09:00", "18:00", "6", "", "", None, "Craft stalls and shops around the marina."),
    ("castries", "Castries market and Derek Walcott Square", "shopping culture food", 120, 0, 0, 1, 0, True, "morning", "07:00", "15:00", "6", "", "", None, "The busy covered market, then the square named for the Nobel-winning poet."),
    ("castries", "Morne Fortune viewpoint and fort", "culture", 90, 5, 2, 1, 0, False, "afternoon", "09:00", "17:00", "", "", "", None, "Hilltop fort ruins with the best view over Castries harbour."),
    ("marigot", "Marigot Bay kayak", "water nature", 120, 40, 25, 2, 8, False, "morning", "08:00", "16:00", "", "", "09:00 14:00", 12, "Paddle round the lagoon and into the mangroves with Lagoon Kayak Co."),
    ("marigot", "Rainforest zipline", "adventure nature", 150, 85, 65, 2, 8, False, "morning", "08:30", "16:30", "", "", "09:00 11:00 13:30", 16, "Twelve lines through the canopy with Canopy Chorus Adventures."),
    ("marigot", "Chocolate-making class", "food", 150, 75, 40, 1, 6, True, "afternoon", "10:00", "17:00", "6", "", "14:00", 12, "Turn St Lucian cocoa into your own bars at Bean Bay Chocolate."),
    ("soufriere", "Gros Piton climb", "hiking adventure", 300, 60, 45, 3, 12, False, "morning", "06:30", "14:00", "", "star", "07:00 08:00", 15, "A steep guided climb to the summit, with views across the island."),
    ("soufriere", "Sulphur Springs mud baths", "wellness nature", 90, 15, 10, 1, 0, False, "any", "09:00", "17:00", "", "star", "", None, "Steam vents of the drive-in volcano, then warm volcanic mud pools."),
    ("soufriere", "Waterfall pools near Soufrière", "nature", 90, 10, 5, 1, 0, True, "afternoon", "09:00", "17:00", "", "", "", None, "Mineral-stained falls in a garden setting, close to town."),
    ("soufriere", "Anse Cochon snorkel trip", "water beaches", 240, 95, 60, 1, 5, False, "morning", "08:30", "16:00", "", "lunch", "09:00", 30, "Boat along the coast to snorkel the reefs, with lunch on the beach."),
    ("soufriere", "Piton Cove spa", "wellness", 120, 150, 150, 1, 16, True, "afternoon", "10:00", "19:00", "", "", "", None, "Massage with a view of the Pitons."),
    # ---- Grenada
    ("grandanse", "Grand Anse Beach", "beaches water", 180, 0, 0, 1, 0, True, "any", "07:00", "18:30", "", "star", "", None, "Two miles of white sand on a calm bay."),
    ("grandanse", "Underwater Sculpture Park snorkel", "water culture", 150, 65, 45, 1, 6, False, "morning", "08:30", "16:00", "", "star", "09:00 13:30", 20, "Snorkel over statues on the sea floor in Molinere Bay, with Spice Isle Snorkel."),
    ("grandanse", "Morne Rouge Bay swim", "beaches", 120, 0, 0, 1, 0, False, "afternoon", "07:00", "18:30", "", "", "", None, "A smaller, quieter beach next to Grand Anse."),
    ("grandanse", "Cinnamon spa", "wellness", 120, 120, 120, 1, 16, True, "afternoon", "10:00", "19:00", "", "", "", None, "Spice-scented treatments in a hillside spa."),
    ("stgeorges", "Fort George and the Carenage", "culture", 120, 5, 2, 1, 0, False, "morning", "08:00", "16:30", "", "star", "", None, "The 1705 fort above St George's, then a stroll round the horseshoe harbour."),
    ("stgeorges", "Spice market", "shopping food", 75, 0, 0, 1, 0, True, "morning", "07:00", "14:00", "6", "", "", None, "Nutmeg, mace, cinnamon and cocoa in Market Square."),
    ("stgeorges", "Grenadian cooking class", "food culture", 180, 80, 40, 1, 6, True, "afternoon", "10:00", "18:00", "06", "", "14:00", 10, "Make oil down, Grenada's national dish, with Pepperpot Kitchen."),
    ("stgeorges", "Sunset catamaran", "water nightlife", 150, 75, 45, 1, 4, False, "evening", "16:30", "19:30", "", "", "16:30", 30, "Sail along the south-west coast at sunset."),
    ("interior", "Grand Etang lake and Seven Sisters falls", "hiking nature", 240, 25, 15, 3, 10, False, "morning", "07:00", "15:00", "", "star", "08:00 09:00", 14, "A muddy guided hike through rainforest to seven waterfalls."),
    ("interior", "Annandale Falls", "nature", 75, 3, 1, 1, 0, True, "any", "08:00", "16:30", "", "", "", None, "An easy, pretty waterfall a short drive from town."),
    ("north", "Gouyave Fish Friday", "food nightlife culture", 180, 0, 0, 1, 0, False, "evening", "18:00", "23:59", "012356", "star dinner", "", None, "The fishing town fills its streets with fish stalls and music every Friday."),
    ("north", "Cocoa estate tour", "food culture nature", 150, 25, 10, 1, 0, True, "morning", "08:00", "16:00", "6", "", "09:30 13:30", 25, "See cocoa grown, dried and made into chocolate at Hillcrest Cocoa Estate."),
    ("north", "River tubing", "adventure water", 120, 55, 40, 2, 8, False, "afternoon", "09:00", "15:30", "", "", "10:00 13:30", 12, "Float down the river through the rainforest with Balthazar River Tubing."),
    # ---- Dominica
    ("valley", "Trafalgar Falls", "nature", 90, 10, 5, 1, 0, False, "morning", "08:00", "17:00", "", "star", "", None, "Twin waterfalls with warm and cool pools at their feet."),
    ("valley", "Boiling Lake hike", "hiking adventure nature", 480, 90, 70, 3, 14, False, "morning", "06:30", "16:30", "", "star lunch", "07:00", 10, "A hard, full-day guided hike to a flooded, boiling fumarole. Packed lunch included."),
    ("valley", "Titou Gorge swim", "water adventure nature", 90, 10, 5, 2, 8, False, "any", "08:00", "17:00", "", "", "", None, "Swim up a narrow gorge to a waterfall inside it."),
    ("valley", "Wotten Waven hot springs", "wellness", 120, 15, 10, 1, 0, False, "afternoon", "09:00", "21:00", "", "", "", None, "Sulphur hot pools in the rainforest at Steam and Stone Baths."),
    ("roseau", "Roseau market and old town walk", "shopping culture food", 120, 0, 0, 1, 0, True, "morning", "06:30", "14:00", "6", "", "", None, "The Saturday market, then the old wooden houses of the capital."),
    ("roseau", "Whale-watching trip", "water nature", 240, 85, 55, 1, 5, False, "afternoon", "13:00", "18:00", "", "star", "14:00", 30, "Look for the sperm whales that live off Dominica all year, with Leeward Whale Watch."),
    ("roseau", "Friday night lime in Roseau", "nightlife food", 150, 0, 0, 1, 18, False, "evening", "20:00", "23:59", "012356", "", "", None, "Live music in the bars along the bayfront."),
    ("scotts", "Champagne Reef snorkel", "water nature", 120, 15, 10, 1, 6, False, "morning", "08:00", "16:00", "", "star", "", None, "Snorkel through warm bubbles rising from the sea floor."),
    ("scotts", "Scotts Head walk and swim", "beaches hiking", 120, 0, 0, 2, 4, False, "afternoon", "07:00", "18:00", "", "", "", None, "Climb the headland between the Atlantic and the Caribbean, then swim."),
    ("portsmouth", "Indian River boat trip", "nature culture", 120, 35, 20, 1, 0, False, "morning", "07:00", "16:00", "", "star", "08:00 10:00 14:00", 12, "Row up a mangrove river with a local guide."),
    ("portsmouth", "Fort Shirley at Cabrits", "culture hiking", 120, 5, 2, 2, 0, False, "afternoon", "08:00", "17:00", "", "", "", None, "Restored 18th-century fort in a national park on a headland."),
    ("portsmouth", "Canyoning in the rainforest", "adventure water", 240, 120, 100, 3, 12, False, "morning", "08:00", "15:00", "", "", "08:30", 8, "Abseil and jump down waterfalls with Extreme Canyon Dominica."),
]

# area, name, cuisine, band (1-4), US$ a head, meals (L/D), closed days, diets (vg vn gf),
# kid friendly, step free, covers, blurb
RESTAURANTS = [
    ("kingstown", "Market Corner Roti", "Roti and Creole", 1, 12, "L", "6", "vg", True, True, 30, "Curry roti and fresh juices, as quick as you like."),
    ("kingstown", "Bayview Kitchen", "Vincentian", 2, 28, "LD", "6", "vg gf", True, False, 40, "Saltfish, breadfruit and fresh fish with a harbour view."),
    ("villa", "Young Island Grill", "Seafood", 3, 55, "D", "", "gf", True, True, 50, "Grilled catch of the day on the waterfront."),
    ("villa", "Cobblestone Café", "Café", 1, 15, "L", "6", "vg vn gf", True, True, 25, "Salads, sandwiches and smoothies by the beach."),
    ("leeward", "Wallilabou Beach Bar", "Caribbean", 2, 25, "L", "", "vg", True, False, 40, "Fish, chicken and cold drinks on the beach."),
    ("windward", "Rabacca Rest Stop", "Local", 1, 12, "L", "6", "vg", True, False, 20, "Stewed chicken and provisions on the road north."),
    ("bequia", "Admiralty Bay Kitchen", "Seafood", 3, 60, "D", "", "gf", True, True, 60, "Lobster in season and fish straight off the boats."),
    ("bequia", "Lower Bay Shack", "Beach bar", 2, 25, "L", "", "vg", True, False, 40, "Toes-in-the-sand lunches."),
    ("bequia", "Green Flash Garden", "Vegetarian", 2, 30, "LD", "0", "vg vn gf", True, True, 30, "Bequia's plant-based garden café."),
    ("bridgetown", "Careenage Cou-Cou", "Bajan", 1, 14, "L", "6", "vg", True, True, 40, "Cou-cou, flying fish and macaroni pie, Bajan style."),
    ("bridgetown", "Boardwalk Brasserie", "International", 3, 50, "LD", "", "vg gf", True, True, 70, "A long menu on the water at Carlisle Bay."),
    ("west", "Holetown Table", "Fine dining", 4, 110, "D", "0", "vg gf", False, True, 40, "Tasting menus on the beach. Book ahead."),
    ("west", "Sandy Lane Deli Bar", "Café", 2, 22, "L", "", "vg vn gf", True, True, 30, "Bowls, wraps and coffee in Holetown."),
    ("south", "Oistins Fish Grill", "Fish fry", 1, 18, "D", "", "gf", True, True, 120, "Plates of grilled fish with macaroni pie and plantain."),
    ("south", "Gap Garden Kitchen", "Caribbean fusion", 3, 55, "D", "1", "vg vn gf", True, True, 50, "Creative plates, plenty of them plant-based."),
    ("south", "Dover Beach Hut", "Beach bar", 2, 24, "L", "", "vg", True, False, 40, "Fish cakes and salads on the sand."),
    ("east", "Bathsheba Lookout", "Bajan", 2, 30, "L", "", "vg gf", True, False, 50, "Buffet lunch on a cliff over the Atlantic."),
    ("rodney", "Reduit Bistro", "International", 3, 50, "D", "", "vg gf", True, True, 70, "Steaks, seafood and pasta near the beach."),
    ("rodney", "Gros Islet Grill Shack", "Street food", 1, 15, "LD", "", "", True, True, 50, "Grilled chicken, fish and fries, quick and cheap."),
    ("castries", "Vigie Bay Kitchen", "St Lucian", 2, 26, "L", "6", "vg gf", True, False, 40, "Green fig and saltfish, the national dish, done well."),
    ("marigot", "Lagoon Deck", "Seafood", 3, 60, "LD", "", "gf", True, True, 60, "On the water in Marigot Bay."),
    ("marigot", "Cocoa Tree Café", "Café", 1, 16, "L", "6", "vg vn gf", True, True, 25, "Sandwiches, salads and cocoa tea."),
    ("soufriere", "Piton Sunset Terrace", "Fine dining", 4, 120, "D", "", "vg vn gf", False, True, 40, "Dinner facing the Pitons. Book ahead."),
    ("soufriere", "Soufrière Creole Pot", "Creole", 1, 15, "L", "6", "vg", True, True, 30, "Bouyon, stews and fresh juice in town."),
    ("stgeorges", "Carenage Café", "Grenadian", 1, 15, "L", "6", "vg", True, True, 40, "Oil down, rotis and callaloo soup."),
    ("stgeorges", "Fort View Terrace", "Caribbean", 3, 45, "D", "0", "vg gf", True, False, 50, "Dinner looking over the harbour lights."),
    ("grandanse", "Grand Anse Beach Grill", "Beach bar", 2, 25, "LD", "", "vg gf", True, True, 80, "Fish tacos and rum punch on the sand."),
    ("grandanse", "Nutmeg & Mace", "Fine dining", 4, 95, "D", "1", "vg vn gf", False, True, 36, "Spice-led tasting menu. Book ahead."),
    ("grandanse", "Green Spice Kitchen", "Vegetarian", 2, 22, "LD", "6", "vg vn gf", True, True, 30, "Callaloo lasagne, lentil roti and fresh juices."),
    ("interior", "Rainforest Rest Stop", "Local", 1, 12, "L", "", "vg", True, False, 30, "Rotis and coconut water at the lake."),
    ("north", "Gouyave Fish Stalls", "Fish fry", 1, 15, "D", "", "gf", True, False, 80, "Fish every way, especially on Fridays."),
    ("north", "Cocoa House Lunch", "Grenadian", 2, 25, "L", "6", "vg gf", True, True, 30, "Lunch on the cocoa estate veranda."),
    ("roseau", "Old Market Kitchen", "Creole", 1, 14, "L", "6", "vg", True, True, 40, "Callaloo, fish broth and local juices."),
    ("roseau", "Bayfront Table", "Caribbean", 3, 45, "D", "", "vg gf", True, True, 50, "Seafood and Creole dishes on the waterfront."),
    ("roseau", "Root & Leaf", "Vegan", 2, 20, "LD", "6", "vg vn gf", True, True, 25, "Dominica's vegan café: provisions, curries and juices."),
    ("valley", "Hot Springs Kitchen", "Creole", 2, 22, "LD", "", "vg gf", True, False, 30, "Simple plates between soaks in the valley."),
    ("scotts", "Scotts Head Fish Hut", "Seafood", 2, 26, "LD", "", "gf", True, False, 40, "Fish caught that morning, by the bay."),
    ("portsmouth", "Purple Turtle Beach Bar", "Beach bar", 2, 22, "LD", "", "vg", True, True, 50, "Burgers, fish and cold drinks on Prince Rupert Bay."),
    ("portsmouth", "Cabrits Lookout", "Creole", 3, 40, "D", "1", "vg gf", True, False, 36, "Sunset dinners near the fort."),
]


def seed_catalogue(db):
    """Fill an empty database with the demo catalogue. Returns {destination code: Destination}."""
    dests = {}
    for code, name, blurb in DESTINATIONS:
        dests[code] = Destination(code=code, name=name, blurb=blurb)
        db.add(dests[code])
    areas = {}
    for dest, key, name, island, lat, lng in AREAS:
        areas[(dest, key)] = Area(destination=dests[dest], name=name, island=island, lat=lat, lng=lng)
        db.add(areas[(dest, key)])
    db.flush()
    keys = [key for _, key, *_ in AREAS]
    assert len(keys) == len(set(keys)), "area keys must be unique"
    by_key = {key: areas[(dest, key)] for dest, key, *_ in AREAS}

    for row in STAYS:
        key, name, style, nightly, sleeps, rooms, kids, step_free, cancel, blurb = row
        db.add(Stay(area=by_key[key], name=name, style=style, nightly_cents=nightly * 100, sleeps=sleeps,
                    rooms_total=rooms, kid_friendly=kids, step_free=step_free, free_cancel_hours=cancel, blurb=blurb))

    for row in ACTIVITIES:
        (key, name, tags, minutes, price, child, energy, min_age, step_free, best, opens, closes, closed,
         flags, starts, capacity, blurb) = row
        a = Activity(area=by_key[key], name=name, blurb=blurb, minutes=minutes, price_cents=price * 100,
                     child_price_cents=child * 100, energy=energy, min_age=min_age, step_free=step_free,
                     best_time=best, opens=t(opens), closes=t(closes), closed_days=closed,
                     includes_lunch="lunch" in flags.split(), includes_dinner="dinner" in flags.split(),
                     highlight="star" in flags.split(), capacity=capacity)
        a.tags = [ActivityTag(tag=tag) for tag in tags.split()]
        a.start_times = [ActivityStart(starts=t(s)) for s in starts.split()]
        db.add(a)

    for row in RESTAURANTS:
        key, name, cuisine, band, avg, meals, closed, diets, kids, step_free, covers, blurb = row
        db.add(Restaurant(area=by_key[key], name=name, cuisine=cuisine, blurb=blurb, price_band=band,
                          avg_cents=avg * 100, lunch="L" in meals, dinner="D" in meals, closed_days=closed,
                          vegetarian="vg" in diets.split(), vegan="vn" in diets.split(),
                          gluten_free="gf" in diets.split(), kid_friendly=kids, step_free=step_free, covers=covers))
    db.flush()
    return dests

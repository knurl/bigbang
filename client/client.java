public class Main {
    public static void main(String[] args) {
	HazelcastInstance hzInstance = Hazelcast.newHazelcastInstance();
	Map<String, String> capitalcities = hzInstance.getMap( "capitals" );
	capitalcities.put( "1", "Tokyo" );
	capitalcities.put( "2", "Paris" );
	capitalcities.put( "3", "Washington" );
	capitalcities.put( "4", "Ankara" );
	capitalcities.put( "5", "Brussels" );
	capitalcities.put( "6", "Amsterdam" );
	capitalcities.put( "7", "New Delhi" );
	capitalcities.put( "8", "London" );
	capitalcities.put( "9", "Berlin" );
	capitalcities.put( "10", "Oslo" );
	capitalcities.put( "11", "Moscow" );
	capitalcities.put( "120", "Stockholm" );
    }
}

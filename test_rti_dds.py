import time
import rti.connextdds as dds
from rti.types.builtin import String

def test_rti_dds():
    # Create a DomainParticipant
    participant = dds.DomainParticipant(domain_id=0)
    
    # Create a Topic
    topic = dds.Topic(participant, "TestTopic", String)
    
    # Create a Publisher and DataWriter
    publisher = dds.Publisher(participant)
    writer = dds.DataWriter(publisher, topic)
    
    # Create a Subscriber and DataReader
    subscriber = dds.Subscriber(participant)
    reader = dds.DataReader(subscriber, topic)
    
    # Write a sample
    sample = String("Hello, RTI DDS!")
    print(f"Writing sample: {sample}")
    writer.write(sample)
    
    # Wait for the sample to be received
    time.sleep(1)
    
    # Read the sample
    samples = reader.take()
    for sample in samples:
        if sample.info.valid:
            print(f"Received sample: {sample.data}")
    
    # Cleanup
    participant.close()

if __name__ == "__main__":
    print("Starting RTI DDS test...")
    try:
        test_rti_dds()
        print("Test completed successfully!")
    except Exception as e:
        print(f"Test failed with error: {e}") 